from typing import List, Dict
from app.core.schema import ResumeFacts
from app.core.domain_detector import detect_search_keywords
from app.core.job_finder import fetch_all_jobs
from app.core.jd_parser import parse_jd
from app.core.scorer import score_resume
from app.core.latex_compiler import render_latex, compile_to_pdf
from app.graph.build_graph import run_optimization_loop

# Jobs below this quick-score aren't worth spending the full critique/edit
# loop's LLM calls on - this is the funnel that keeps the pipeline
# affordable even when the combined sources return many matches.
PREFILTER_THRESHOLD = 60.0


def _is_rate_limit_error(e: Exception) -> bool:
    """Detects a quota/rate-limit failure from Groq regardless of exact
    exception type, since langchain wraps the underlying groq error."""
    msg = str(e).lower()
    return "rate_limit" in msg or "429" in msg or "quota" in msg


def run_discovery_pipeline(
    facts: ResumeFacts,
    max_jobs_to_scan: int = 50,
    target_score: float = 93.0,
) -> List[Dict]:
    """
    Full pipeline:
    1. Detect search keywords from the resume
    2. Fetch matching jobs from RemoteOK, Himalayas, and Remotive
    3. Quick-score every job (cheap, no critique/edit LLM calls)
    4. Fully tailor (score -> critique -> edit loop -> PDF) only jobs that
       clear PREFILTER_THRESHOLD
    Stops gracefully and returns whatever was gathered so far if Groq's
    daily quota runs out mid-batch, instead of crashing and losing everything.
    """
    keywords = detect_search_keywords(facts)
    jobs = fetch_all_jobs(keywords, max_results=max_jobs_to_scan)

    results = []
    quota_exhausted = False

    for job in jobs:
        if not job["description"]:
            continue

        try:
            jd = parse_jd(job["description"])
        except Exception as e:
            if _is_rate_limit_error(e):
                quota_exhausted = True
                break
            results.append({
                "title": job["title"], "company": job["company"], "url": job["url"],
                "source": job.get("source", ""), "location": job.get("location", ""),
                "quick_score": None, "error": f"JD parsing failed: {e}", "tailored": False,
            })
            continue

        try:
            quick_score = score_resume(jd, facts)["overall_score"]
        except Exception as e:
            results.append({
                "title": job["title"], "company": job["company"], "url": job["url"],
                "source": job.get("source", ""), "location": job.get("location", ""),
                "quick_score": None, "error": f"Scoring failed: {e}", "tailored": False,
            })
            continue

        result = {
            "title": job["title"], "company": job["company"], "url": job["url"],
            "source": job.get("source", ""), "location": job.get("location", ""),
            "quick_score": quick_score, "tailored": False,
        }

        if quick_score >= PREFILTER_THRESHOLD:
            try:
                loop_result = run_optimization_loop(jd, facts, target_score=target_score)
            except Exception as e:
                if _is_rate_limit_error(e):
                    result["note"] = "Groq daily quota reached before full tailoring could run"
                    results.append(result)
                    quota_exhausted = True
                    break
                result["error"] = f"Optimization loop failed: {e}"
                results.append(result)
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

    if quota_exhausted:
        print(f"\nGroq daily quota reached after processing {len(results)} jobs. "
              f"Quota resets daily. Partial results returned below.")

    return results


if __name__ == "__main__":
    with open("data/resume_facts.json", "r", encoding="utf-8") as f:
        facts = ResumeFacts.model_validate_json(f.read())

    results = run_discovery_pipeline(facts, max_jobs_to_scan=15)

    print(f"\nScanned {len(results)} jobs\n")
    for r in results:
        if r.get("quick_score") is None:
            print(f"[SKIPPED] {r['title']} @ {r['company']} - {r.get('error')}")
        elif r["tailored"]:
            print(f"[TAILORED] {r['title']} @ {r['company']} - "
                  f"quick={r['quick_score']} final={r.get('final_score')} -> {r['pdf_filename']}")
        elif r.get("note"):
            print(f"[QUOTA HIT] {r['title']} @ {r['company']} - quick_score={r['quick_score']} - {r['note']}")
        else:
            print(f"[SCANNED]  {r['title']} @ {r['company']} - quick_score={r['quick_score']}")