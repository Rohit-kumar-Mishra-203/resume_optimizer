import requests
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

HEADERS = {"User-Agent": "Mozilla/5.0 (personal resume tool; contact: you@example.com)"}


def _matches(text: str, keywords_lower: List[str]) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords_lower)


def fetch_remoteok_jobs(keywords: List[str], max_results: int = 100) -> List[Dict]:
    """Free, no auth. Global remote jobs."""
    try:
        resp = requests.get("https://remoteok.com/api", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        if raw and "legal" in raw[0]:
            raw = raw[1:]
    except Exception as e:
        print(f"[RemoteOK] fetch failed: {e}")
        return []

    keywords_lower = [k.lower() for k in keywords]
    matched = []
    for job in raw:
        searchable = " ".join([job.get("position", ""), job.get("company", ""), " ".join(job.get("tags", []))])
        if _matches(searchable, keywords_lower):
            matched.append({
                "title": job.get("position", "Unknown role"),
                "company": job.get("company", "Unknown company"),
                "url": job.get("url", ""),
                "description": job.get("description", ""),
                "location": "Remote",
                "source": "RemoteOK",
            })
        if len(matched) >= max_results:
            break
    return matched


def fetch_himalayas_jobs(keywords: List[str], max_results: int = 20) -> List[Dict]:
    """Free, no auth. Global remote jobs. Capped at 20 per request by Himalayas."""
    try:
        resp = requests.get(
            "https://himalayas.app/jobs/api", params={"limit": 20}, headers=HEADERS, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("jobs", [])
    except Exception as e:
        print(f"[Himalayas] fetch failed: {e}")
        return []

    keywords_lower = [k.lower() for k in keywords]
    matched = []
    for job in raw:
        title = job.get("title", "")
        company = job.get("companyName", job.get("company", ""))
        searchable = f"{title} {company}"
        if _matches(searchable, keywords_lower):
            matched.append({
                "title": title or "Unknown role",
                "company": company or "Unknown company",
                "url": job.get("applicationLink", job.get("url", "")),
                "description": job.get("description", ""),
                "location": "Remote",
                "source": "Himalayas",
            })
        if len(matched) >= max_results:
            break
    return matched


def fetch_remotive_jobs(keywords: List[str], max_results: int = 50) -> List[Dict]:
    """Free, no auth. Global remote jobs. Supports server-side search param."""
    matched = []
    for kw in keywords[:3]:  # a few targeted queries rather than one huge fetch
        try:
            resp = requests.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": kw},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for job in data.get("jobs", []):
                matched.append({
                    "title": job.get("title", "Unknown role"),
                    "company": job.get("company_name", "Unknown company"),
                    "url": job.get("url", ""),
                    "description": job.get("description", ""),
                    "location": "Remote",
                    "source": "Remotive",
                })
        except Exception as e:
            print(f"[Remotive] fetch failed for '{kw}': {e}")
        if len(matched) >= max_results:
            break
    return matched[:max_results]


def _dedupe(jobs: List[Dict]) -> List[Dict]:
    """Removes near-duplicate listings (same title + company) that
    different aggregators sometimes both return."""
    seen = set()
    unique = []
    for job in jobs:
        key = (job["title"].strip().lower(), job["company"].strip().lower())
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def fetch_all_jobs(keywords: List[str], max_results: int = 100) -> List[Dict]:
    """
    Combines global remote sources (RemoteOK, Himalayas, Remotive), deduping
    overlapping results. Each source failing independently doesn't block
    the others.
    """
    all_jobs = []
    all_jobs += fetch_remoteok_jobs(keywords, max_results=max_results)
    all_jobs += fetch_himalayas_jobs(keywords, max_results=max_results)
    all_jobs += fetch_remotive_jobs(keywords, max_results=max_results)

    unique_jobs = _dedupe(all_jobs)
    return unique_jobs[:max_results]


if __name__ == "__main__":
    test_keywords = ["Machine Learning", "NLP", "AI Engineer"]
    jobs = fetch_all_jobs(test_keywords, max_results=30)
    print(f"Found {len(jobs)} unique matching jobs across all sources\n")
    for job in jobs:
        print(f"[{job['source']}] {job['title']} @ {job['company']} ({job['location']})")