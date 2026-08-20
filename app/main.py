import os
import json
import threading
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
from app.core.batch_pipeline import (
    run_discovery_pipeline, is_discovery_running, CHECKPOINT_PATH, CURRENT_RUN_PATH
)
from app.core.applied_tracker import (
    mark_applied, unmark_applied, get_applied_jobs, update_status, get_experiment_summary
)

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
    ats_score: float | None = None


class UpdateStatusRequest(BaseModel):
    title: str
    company: str
    status: str
    notes: str = ""


@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
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
    if not RESUME_FACTS_PATH.exists():
        raise HTTPException(status_code=400, detail="No resume on file yet - call /upload-resume first.")

    facts = ResumeFacts.model_validate_json(RESUME_FACTS_PATH.read_text(encoding="utf-8"))
    jd = parse_jd(request.jd_text)

    result = run_optimization_loop(
        jd, facts, target_score=request.target_score, max_iterations=request.max_iterations
    )

    tex_source = render_latex(result["facts"])
    pdf_filename = f"resume_{jd.job_title.replace(' ', '_')}"
    pdf_path = compile_to_pdf(tex_source, output_filename=pdf_filename)

    genuine_gaps = []
    if result["status"] == "plateaued" and result["critique"]:
        genuine_gaps = [item.description for item in result["critique"].items if item.is_genuine_gap]

    return OptimizeResponse(
        status=result["status"],
        iterations_run=result["iteration"],
        score_history=result["score_history"],
        final_score=result["score_history"][-1],
        pdf_filename=pdf_path.name,
        genuine_gaps=genuine_gaps,
    )


@app.post("/start-discovery")
async def start_discovery(request: DiscoverRequest):
    """Starts discovery as a background thread so the frontend can poll
    live progress instead of waiting on one long blocking HTTP request."""
    if not RESUME_FACTS_PATH.exists():
        raise HTTPException(status_code=400, detail="No resume on file yet - call /upload-resume first.")
    if is_discovery_running():
        return {"message": "Discovery already running"}

    facts = ResumeFacts.model_validate_json(RESUME_FACTS_PATH.read_text(encoding="utf-8"))

    def _run():
        run_discovery_pipeline(
            facts, max_jobs_to_scan=request.max_jobs_to_scan, target_score=request.target_score
        )

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "Discovery started"}


@app.get("/discovery-progress")
async def discovery_progress():
    """Returns only THIS run's results, not the full all-time history."""
    results = []
    if CURRENT_RUN_PATH.exists():
        results = json.loads(CURRENT_RUN_PATH.read_text(encoding="utf-8"))
    return {"results": results, "is_running": is_discovery_running()}

@app.post("/mark-applied")
async def mark_applied_endpoint(request: AppliedRequest):
    mark_applied(request.title, request.company, request.url, request.source, request.ats_score)
    return {"message": "Marked as applied"}


@app.post("/unmark-applied")
async def unmark_applied_endpoint(request: AppliedRequest):
    unmark_applied(request.title, request.company)
    return {"message": "Unmarked"}


@app.get("/applied-jobs")
async def applied_jobs_endpoint():
    return {"applied_jobs": get_applied_jobs()}


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


@app.get("/download/{filename}")
async def download_pdf(filename: str):
    file_path = GENERATED_DIR / filename

    if not file_path.resolve().is_relative_to(GENERATED_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="application/pdf", filename=filename)