import os
import json
import threading
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.schema import ResumeFacts
from app.core.resume_parser import parse_resume
from app.core.jd_parser import parse_jd
from app.core.latex_compiler import render_latex, compile_to_pdf
from app.graph.build_graph import run_optimization_loop
from app.core.batch_pipeline import run_discovery_pipeline, is_discovery_running
from app.core.applied_tracker import mark_applied, unmark_applied, get_applied_jobs, update_status, get_experiment_summary
from app.core.auth import get_current_user
from app.core.user_paths import (
    resume_facts_path, base_resume_path, generated_dir, current_run_path
)

app = FastAPI(title="Resume Optimizer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your real frontend domain before public launch
    allow_methods=["*"],
    allow_headers=["*"],
)


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
async def upload_resume(file: UploadFile = File(...), user_id: str = Depends(get_current_user)):
    contents = await file.read()
    base_resume_path(user_id).write_bytes(contents)

    try:
        resume_text = contents.decode("utf-8")
    except UnicodeDecodeError:
        resume_text = contents.decode("latin-1")

    facts = parse_resume(resume_text)
    resume_facts_path(user_id).write_text(facts.model_dump_json(indent=2), encoding="utf-8")

    return {
        "message": "Resume parsed successfully",
        "experience_count": len(facts.experience),
        "project_count": len(facts.projects),
        "skill_count": sum(len(s.items) for s in facts.skills),
    }


@app.post("/optimize", response_model=OptimizeResponse)
async def optimize_resume(request: OptimizeRequest, user_id: str = Depends(get_current_user)):
    path = resume_facts_path(user_id)
    if not path.exists():
        raise HTTPException(status_code=400, detail="No resume on file yet - call /upload-resume first.")

    facts = ResumeFacts.model_validate_json(path.read_text(encoding="utf-8"))
    jd = parse_jd(request.jd_text)

    result = run_optimization_loop(
        jd, facts, target_score=request.target_score, max_iterations=request.max_iterations
    )

    tex_source = render_latex(result["facts"])
    pdf_filename = f"resume_{jd.job_title.replace(' ', '_')}"
    pdf_path = compile_to_pdf(tex_source, output_filename=str(generated_dir(user_id) / pdf_filename))

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
async def start_discovery(request: DiscoverRequest, user_id: str = Depends(get_current_user)):
    path = resume_facts_path(user_id)
    if not path.exists():
        raise HTTPException(status_code=400, detail="No resume on file yet - call /upload-resume first.")
    if is_discovery_running(user_id):
        return {"message": "Discovery already running"}

    facts = ResumeFacts.model_validate_json(path.read_text(encoding="utf-8"))

    def _run():
        run_discovery_pipeline(
            facts, user_id=user_id, max_jobs_to_scan=request.max_jobs_to_scan, target_score=request.target_score
        )

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "Discovery started"}


@app.get("/discovery-progress")
async def discovery_progress(user_id: str = Depends(get_current_user)):
    results = []
    cr_path = current_run_path(user_id)
    if cr_path.exists():
        results = json.loads(cr_path.read_text(encoding="utf-8"))
    return {"results": results, "is_running": is_discovery_running(user_id)}


@app.post("/mark-applied")
async def mark_applied_endpoint(request: AppliedRequest, user_id: str = Depends(get_current_user)):
    mark_applied(user_id, request.title, request.company, request.url, request.source, request.ats_score)
    return {"message": "Marked as applied"}


@app.post("/unmark-applied")
async def unmark_applied_endpoint(request: AppliedRequest, user_id: str = Depends(get_current_user)):
    unmark_applied(user_id, request.title, request.company)
    return {"message": "Unmarked"}


@app.get("/applied-jobs")
async def applied_jobs_endpoint(user_id: str = Depends(get_current_user)):
    return {"applied_jobs": get_applied_jobs(user_id)}


@app.post("/update-application-status")
async def update_status_endpoint(request: UpdateStatusRequest, user_id: str = Depends(get_current_user)):
    try:
        update_status(user_id, request.title, request.company, request.status, request.notes)
        return {"message": "Status updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/experiment-summary")
async def experiment_summary_endpoint(days: int = 30, user_id: str = Depends(get_current_user)):
    return get_experiment_summary(user_id, days=days)


@app.get("/download/{filename}")
async def download_pdf(filename: str, user_id: str = Depends(get_current_user)):
    file_path = generated_dir(user_id) / filename

    if not file_path.resolve().is_relative_to(generated_dir(user_id).resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="application/pdf", filename=filename)