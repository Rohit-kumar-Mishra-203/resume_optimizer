import json
import time
from pathlib import Path
from typing import List, Dict
from app.core.schema import ResumeFacts
from app.core.domain_detector import detect_search_keywords
from app.core.job_finder import fetch_all_jobs
from app.core.jd_parser import parse_jd
from app.core.scorer import score_resume
from app.core.latex_compiler import render_latex, compile_to_pdf
from app.graph.build_graph import run_optimization_loop

PREFILTER_THRESHOLD = 60.0
CHECKPOINT_PATH = Path("data/discovery_checkpoint.json")

WAIT_SECONDS_BETWEEN_RETRIES = 600  # 10 minutes
MAX_WAIT_HOURS = 26  # safety cap so it can't loop forever if something's wrong


def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "rate_limit" in msg or "429" in msg or "quota" in msg


def _job_key(job: Dict) -> str:
    return f"{job['title'].strip().lower()}::{job['company'].strip().lower()}"


def _load_checkpoint() -> Dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"processed_keys": [], "results": []}


def _save_checkpoint(checkpoint: Dict) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def _call_with_quota_retry(fn, *args, **kwargs):
    """
    Calls fn(*args, **kwargs). If it fails on a rate limit (after our
    key-rotation in groq_client already tried every configured key), waits
    and retries automatically instead of giving up - so a single run of
    this pipeline can push through a full daily quota reset on its own,
    with no manual rerun needed. Capped at MAX_WAIT_HOURS as a safety net.
    """
    total_waited = 0
    max_wait_seconds = MAX_WAIT_HOURS * 3600

    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if not _is_rate_limit_error(e):
                raise  # a real bug, not a quota issue - surface it immediately

            if total_waited >= max_wait_seconds:
                raise RuntimeError(
                    f"Still rate-limited after waiting {MAX_WAIT_HOURS} hours - giving up."
                ) from e

            mins = WAIT_SECONDS_BETWEEN_RETRIES // 60
            print(f"  Quota exhausted on all keys. Waiting {mins} minutes before retrying "
                  f"(waited {total_waited // 60} min so far)...")
            time.sleep(WAIT_SECONDS_BETWEEN_RETRIES)
            total_waited += WAIT_SECONDS_BETWEEN_RETRIES


def run_discovery_pipeline(
    facts: ResumeFacts,
    max_jobs_to_scan: int = 50,
    target_score: float = 93.0,
    resume_from_checkpoint: bool = True,
) -> List[Dict]:
    """
    Runs the full discovery pipeline to completion in ONE call - if quota
    runs out, it automatically waits and retries rather than stopping, so
    you don't need to manually rerun this. Checkpointing still protects
    against a hard interruption (e.g. closing the terminal) separately.
    """
    checkpoint = _load_checkpoint() if resume_from_checkpoint else {"processed_keys": [], "results": []}
    processed_keys = set(checkpoint["processed_keys"])
    results = checkpoint["results"]

    keywords = detect_search_keywords(facts)
    jobs = fetch_all_jobs(keywords, max_results=max_jobs_to_scan)

    print(f"\nScanning {len(jobs)} jobs found...")
    for idx, job in enumerate(jobs, 1):
        key = _job_key(job)
        if key in processed_keys:
            print(f"[{idx}/{len(jobs)}] {job['title']} @ {job['company']} - already processed, skipping")
            continue

        print(f"[{idx}/{len(jobs)}] {job['title']} @ {job['company']}...")

        if not job["description"]:
            processed_keys.add(key)
            continue

        try:
            jd = _call_with_quota_retry(parse_jd, job["description"])
        except Exception as e:
            results.append({
                "title": job["title"], "company": job["company"], "url": job["url"],
                "source": job.get("source", ""), "location": job.get("location", ""),
                "quick_score": None, "error": f"JD parsing failed: {e}", "tailored": False,
            })
            processed_keys.add(key)
            _save_checkpoint({"processed_keys": list(processed_keys), "results": results})
            continue

        try:
            quick_score = score_resume(jd, facts)["overall_score"]
        except Exception as e:
            results.append({
                "title": job["title"], "company": job["company"], "url": job["url"],
                "source": job.get("source", ""), "location": job.get("location", ""),
                "quick_score": None, "error": f"Scoring failed: {e}", "tailored": False,
            })
            processed_keys.add(key)
            _save_checkpoint({"processed_keys": list(processed_keys), "results": results})
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
                results.append(result)
                processed_keys.add(key)
                _save_checkpoint({"processed_keys": list(processed_keys), "results": results})
                continue

            final_score = loop_result["score_history"][-1]
            result["final_score"] = final_score
            result["status"] = loop_result["status"]

            if final_score >= target_score:
                tex_source = render_latex(loop_result["facts"])
                safe_title = job["title"].replace(" ", "_").replace("/", "_")[:40]
                pdf_path = compile_to_pdf(tex_source, output_filename=f"resume_{safe_title}")
                result["tailored"] = True
                result["pdf_filename"] = pdf_path.name

        results.append(result)
        processed_keys.add(key)
        _save_checkpoint({"processed_keys": list(processed_keys), "results": results})

    print(f"\nDone. Processed {len(results)} jobs total.")
    return results


def clear_checkpoint() -> None:
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


if __name__ == "__main__":
    with open("data/resume_facts.json", "r", encoding="utf-8") as f:
        facts = ResumeFacts.model_validate_json(f.read())

    results = run_discovery_pipeline(facts, max_jobs_to_scan=15)

    print(f"\nScanned {len(results)} jobs total\n")
    for r in results:
        if r.get("quick_score") is None:
            print(f"[SKIPPED] {r['title']} @ {r['company']} - {r.get('error')}")
        elif r["tailored"]:
            print(f"[TAILORED] {r['title']} @ {r['company']} - "
                  f"quick={r['quick_score']} final={r.get('final_score')} -> {r['pdf_filename']}")
        else:
            print(f"[SCANNED]  {r['title']} @ {r['company']} - quick_score={r['quick_score']}")