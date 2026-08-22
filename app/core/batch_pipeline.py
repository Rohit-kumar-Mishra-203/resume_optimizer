import json
import time
from typing import List, Dict
from app.core.schema import ResumeFacts
from app.core.domain_detector import detect_search_keywords
from app.core.job_finder import fetch_all_jobs
from app.core.jd_parser import parse_jd
from app.core.scorer import score_resume
from app.core.latex_compiler import render_latex, compile_to_pdf
from app.graph.build_graph import run_optimization_loop
from app.core.user_paths import checkpoint_path, current_run_path, status_path, generated_dir

PREFILTER_THRESHOLD = 60.0
WAIT_SECONDS_BETWEEN_RETRIES = 600
MAX_WAIT_HOURS = 26


def _set_running(user_id: str, running: bool) -> None:
    status_path(user_id).write_text(json.dumps({"is_running": running}), encoding="utf-8")


def is_discovery_running(user_id: str) -> bool:
    p = status_path(user_id)
    if not p.exists():
        return False
    return json.loads(p.read_text(encoding="utf-8")).get("is_running", False)


def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "rate_limit" in msg or "429" in msg or "quota" in msg


def _job_key(job: Dict) -> str:
    return f"{job['title'].strip().lower()}::{job['company'].strip().lower()}"


def _load_checkpoint(user_id: str) -> Dict:
    p = checkpoint_path(user_id)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"processed_keys": [], "results": []}


def _save_checkpoint(user_id: str, checkpoint: Dict) -> None:
    checkpoint_path(user_id).write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def _save_current_run(user_id: str, results: List[Dict]) -> None:
    current_run_path(user_id).write_text(json.dumps(results, indent=2), encoding="utf-8")


def _call_with_quota_retry(fn, *args, **kwargs):
    total_waited = 0
    max_wait_seconds = MAX_WAIT_HOURS * 3600
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if not _is_rate_limit_error(e):
                raise
            if total_waited >= max_wait_seconds:
                raise RuntimeError(f"Still rate-limited after waiting {MAX_WAIT_HOURS} hours - giving up.") from e
            mins = WAIT_SECONDS_BETWEEN_RETRIES // 60
            print(f"  Quota exhausted on all keys. Waiting {mins} minutes before retrying "
                  f"(waited {total_waited // 60} min so far)...")
            time.sleep(WAIT_SECONDS_BETWEEN_RETRIES)
            total_waited += WAIT_SECONDS_BETWEEN_RETRIES


def run_discovery_pipeline(
    facts: ResumeFacts,
    user_id: str,
    max_jobs_to_scan: int = 50,
    target_score: float = 93.0,
    resume_from_checkpoint: bool = True,
) -> List[Dict]:
    """
    Per-user discovery pipeline. Every read/write is scoped to user_id via
    user_paths, so different users' checkpoints, in-progress status, and
    results never mix.
    """
    _set_running(user_id, True)
    try:
        _save_current_run(user_id, [])
        checkpoint = _load_checkpoint(user_id) if resume_from_checkpoint else {"processed_keys": [], "results": []}
        processed_keys = set(checkpoint["processed_keys"])
        all_time_results = checkpoint["results"]
        new_results: List[Dict] = []

        keywords = detect_search_keywords(facts)
        jobs = fetch_all_jobs(keywords, max_results=max_jobs_to_scan)

        print(f"\n[{user_id}] Scanning {len(jobs)} jobs found...")
        for idx, job in enumerate(jobs, 1):
            key = _job_key(job)
            if key in processed_keys:
                print(f"[{idx}/{len(jobs)}] {job['title']} @ {job['company']} - already seen, skipping")
                continue

            print(f"[{idx}/{len(jobs)}] {job['title']} @ {job['company']}...")

            if not job["description"]:
                processed_keys.add(key)
                continue

            try:
                jd = _call_with_quota_retry(parse_jd, job["description"])
            except Exception as e:
                result = {
                    "title": job["title"], "company": job["company"], "url": job["url"],
                    "source": job.get("source", ""), "location": job.get("location", ""),
                    "quick_score": None, "error": f"JD parsing failed: {e}", "tailored": False,
                }
                new_results.append(result)
                all_time_results.append(result)
                processed_keys.add(key)
                _save_checkpoint(user_id, {"processed_keys": list(processed_keys), "results": all_time_results})
                _save_current_run(user_id, new_results)
                continue

            try:
                quick_score = score_resume(jd, facts)["overall_score"]
            except Exception as e:
                result = {
                    "title": job["title"], "company": job["company"], "url": job["url"],
                    "source": job.get("source", ""), "location": job.get("location", ""),
                    "quick_score": None, "error": f"Scoring failed: {e}", "tailored": False,
                }
                new_results.append(result)
                all_time_results.append(result)
                processed_keys.add(key)
                _save_checkpoint(user_id, {"processed_keys": list(processed_keys), "results": all_time_results})
                _save_current_run(user_id, new_results)
                continue

            result = {
                "title": job["title"], "company": job["company"], "url": job["url"],
                "source": job.get("source", ""), "location": job.get("location", ""),
                "quick_score": quick_score, "tailored": False,
            }

            if quick_score >= PREFILTER_THRESHOLD:
                try:
                    loop_result = _call_with_quota_retry(
                        run_optimization_loop, jd, facts, target_score=target_score
                    )
                except Exception as e:
                    result["error"] = f"Optimization loop failed: {e}"
                    new_results.append(result)
                    all_time_results.append(result)
                    processed_keys.add(key)
                    _save_checkpoint(user_id, {"processed_keys": list(processed_keys), "results": all_time_results})
                    _save_current_run(user_id, new_results)
                    continue

                final_score = loop_result["score_history"][-1]
                result["final_score"] = final_score
                result["status"] = loop_result["status"]

                if final_score >= target_score:
                    tex_source = render_latex(loop_result["facts"])
                    safe_title = job["title"].replace(" ", "_").replace("/", "_")[:40]
                    out_path = str(generated_dir(user_id) / f"resume_{safe_title}")
                    pdf_path = compile_to_pdf(tex_source, output_filename=out_path)
                    result["tailored"] = True
                    result["pdf_filename"] = pdf_path.name

            new_results.append(result)
            all_time_results.append(result)
            processed_keys.add(key)
            _save_checkpoint(user_id, {"processed_keys": list(processed_keys), "results": all_time_results})
            _save_current_run(user_id, new_results)

        print(f"\n[{user_id}] Done. {len(new_results)} new jobs found this run "
              f"({len(all_time_results)} total ever processed).")
        return new_results
    finally:
        _set_running(user_id, False)


def clear_checkpoint(user_id: str) -> None:
    p = checkpoint_path(user_id)
    if p.exists():
        p.unlink()