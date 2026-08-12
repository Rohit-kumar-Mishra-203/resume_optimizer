import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.schema import ResumeFacts
from app.core.resume_parser import parse_resume
from app.core.jd_parser import parse_jd
from app.core.latex_compiler import render_latex, compile_to_pdf
from app.graph.build_graph import run_optimization_loop
from app.core.batch_pipeline import run_discovery_pipeline
from app.core.applied_tracker import mark_applied, unmark_applied, get_applied_jobs, update_status, get_experiment_summary


app = FastAPI(title="Resume Optimizer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path("data")
RESUME_FACTS_PATH = DATA_DIR / "resume_facts.json"
BASE_RESUME_PATH = DATA_DIR / "base_resume.tex"
GENERATED_DIR = DATA_DIR / "generated"


class OptimizeRequest(BaseModel):
    jd_text: str
    target_score: float = 93.0
    max_iterations: int = 6


class OptimizeResponse(BaseModel):
    status: str
    iterations_run: int
    score_history: list[float]
    final_score: float
    pdf_filename: str
    genuine_gaps: list[str]


class DiscoverRequest(BaseModel):
    max_jobs_to_scan: int = 30
    target_score: float = 93.0
    
class AppliedRequest(BaseModel):
    title: str
    company: str
    url: str = ""
    source: str = ""
    
class UpdateStatusRequest(BaseModel):
    title: str
    company: str
    status: str
    notes: str = ""    
    
@app.post("/update-application-status")
async def update_status_endpoint(request: UpdateStatusRequest):
    try:
        update_status(request.title, request.company, request.status, request.notes)
        return {"message": "Status updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/experiment-summary")
async def experiment_summary_endpoint(days: int = 30):
    return get_experiment_summary(days=days)    
    
@app.post("/mark-applied")
async def mark_applied_endpoint(request: AppliedRequest):
    mark_applied(request.title, request.company, request.url, request.source)
    return {"message": "Marked as applied"}


@app.post("/unmark-applied")
async def unmark_applied_endpoint(request: AppliedRequest):
    unmark_applied(request.title, request.company)
    return {"message": "Unmarked"}


@app.get("/applied-jobs")
async def applied_jobs_endpoint():
    return {"applied_jobs": get_applied_jobs()}        


@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    One-time setup: accepts a .tex resume file, saves it, and parses it
    into structured resume_facts.json - the source of truth for every
    future optimization run.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    contents = await file.read()

    BASE_RESUME_PATH.write_bytes(contents)

    try:
        resume_text = contents.decode("utf-8")
    except UnicodeDecodeError:
        resume_text = contents.decode("latin-1")

    facts = parse_resume(resume_text)

    RESUME_FACTS_PATH.write_text(facts.model_dump_json(indent=2), encoding="utf-8")

    return {
        "message": "Resume parsed successfully",
        "experience_count": len(facts.experience),
        "project_count": len(facts.projects),
        "skill_count": sum(len(s.items) for s in facts.skills),
    }


@app.post("/optimize", response_model=OptimizeResponse)
async def optimize_resume(request: OptimizeRequest):
    """
    Main endpoint: takes a job description, runs the full score -> critique
    -> edit loop against the stored resume_facts.json, then compiles the
    final (possibly improved) resume into a real PDF.
    """
    if not RESUME_FACTS_PATH.exists():
        raise HTTPException(
            status_code=400,
            detail="No resume on file yet - call /upload-resume first.",
        )

    facts = ResumeFacts.model_validate_json(RESUME_FACTS_PATH.read_text(encoding="utf-8"))
    jd = parse_jd(request.jd_text)

    result = run_optimization_loop(
        jd,
        facts,
        target_score=request.target_score,
        max_iterations=request.max_iterations,
    )

    tex_source = render_latex(result["facts"])
    pdf_filename = f"resume_{jd.job_title.replace(' ', '_')}"
    pdf_path = compile_to_pdf(tex_source, output_filename=pdf_filename)

    genuine_gaps = []
    if result["status"] == "plateaued" and result["critique"]:
        genuine_gaps = [
            item.description for item in result["critique"].items if item.is_genuine_gap
        ]

    return OptimizeResponse(
        status=result["status"],
        iterations_run=result["iteration"],
        score_history=result["score_history"],
        final_score=result["score_history"][-1],
        pdf_filename=pdf_path.name,
        genuine_gaps=genuine_gaps,
    )


@app.post("/discover-and-optimize")
async def discover_and_optimize(request: DiscoverRequest):
    """
    Automatic pipeline: detects your domain from your resume, searches
    RemoteOK for matching jobs, quick-scores every match, and fully
    tailors resumes (score -> critique -> edit loop -> PDF) for the
    ones that clear the target score.
    """
    if not RESUME_FACTS_PATH.exists():
        raise HTTPException(
            status_code=400,
            detail="No resume on file yet - call /upload-resume first.",
        )

    facts = ResumeFacts.model_validate_json(RESUME_FACTS_PATH.read_text(encoding="utf-8"))
    results = run_discovery_pipeline(
        facts,
        max_jobs_to_scan=request.max_jobs_to_scan,
        target_score=request.target_score,
    )
    return {"results": results}


@app.get("/download/{filename}")
async def download_pdf(filename: str):
    """Serves a generated PDF for download by the frontend."""
    file_path = GENERATED_DIR / filename

    if not file_path.resolve().is_relative_to(GENERATED_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="application/pdf", filename=filename)