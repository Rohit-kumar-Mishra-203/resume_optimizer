import os
import requests
import feedparser
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

HEADERS = {"User-Agent": "Mozilla/5.0 (personal resume tool; contact: you@example.com)"}


def _matches(text: str, keywords_lower: List[str]) -> bool:
    # Normalize hyphens to spaces before comparing - job board categories/tags
    # are frequently hyphenated (e.g. "Machine-Learning", "AI-Engineering"),
    # while our search keywords use spaces ("machine learning"). Without this,
    # a plain substring check silently misses nearly every category-based
    # match, since "machine learning" never appears literally inside
    # "machine-learning" as a substring.
    normalized = text.lower().replace("-", " ").replace("_", " ")
    return any(kw in normalized for kw in keywords_lower)


# ---------- No-key sources ----------

def fetch_remoteok_jobs(keywords: List[str], max_results: int = 100) -> List[Dict]:
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


def fetch_himalayas_jobs(keywords: List[str], max_results: int = 100) -> List[Dict]:
    """
    Himalayas caps each request at 20 jobs, so we paginate using the
    `offset` param to gather more. Matching now checks categories and
    description too, not just title/company - the real domain signal
    (e.g. "AI-Sales", "Machine-Learning") often lives in categories,
    not the job title itself.
    """
    keywords_lower = [k.lower() for k in keywords]
    matched = []
    offset = 0
    page_size = 20
    max_pages = 50  # cap pagination depth - avoids hammering Himalayas into a 429

    for _ in range(max_pages):
        if len(matched) >= max_results:
            break
        try:
            resp = requests.get(
                "https://himalayas.app/jobs/api",
                params={"limit": page_size, "offset": offset},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[Himalayas] fetch failed at offset {offset}: {e}")
            break

        raw = data.get("jobs", [])
        if not raw:
            break  # no more pages

        for job in raw:
            title = job.get("title", "")
            company = job.get("companyName", "")
            categories = " ".join(job.get("categories", []))
            description = job.get("excerpt", job.get("description", ""))
            searchable = f"{title} {company} {categories} {description}"

            if _matches(searchable, keywords_lower):
                matched.append({
                    "title": title or "Unknown role",
                    "company": company or "Unknown company",
                    "url": job.get("applicationLink", ""),
                    "description": job.get("description", job.get("excerpt", "")),
                    "location": "Remote",
                    "source": "Himalayas",
                })
            if len(matched) >= max_results:
                break

        total_count = data.get("totalCount", 0)
        offset += page_size
        if offset >= total_count:
            break  # reached the end of available jobs

    return matched

'''
def fetch_remotive_jobs(keywords: List[str], max_results: int = 50) -> List[Dict]:
    """
    Remotive's own `search` param is loose (returns many unrelated results),
    so we re-filter client-side against title/company/description too,
    the same pattern used for the other sources.
    """
    keywords_lower = [k.lower() for k in keywords]
    matched = []
    for kw in keywords[:3]:
        try:
            resp = requests.get(
                "https://remotive.com/api/remote-jobs", params={"search": kw}, headers=HEADERS, timeout=15
            )
            resp.raise_for_status()
            for job in resp.json().get("jobs", []):
                title = job.get("title", "")
                company = job.get("company_name", "")
                category = job.get("category", "")
                searchable = f"{title} {company} {category}"
                if _matches(searchable, keywords_lower):
                    matched.append({
                        "title": title or "Unknown role",
                        "company": company or "Unknown company",
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


def fetch_arbeitnow_jobs(keywords: List[str], max_results: int = 50) -> List[Dict]:
    """Free, no auth. Mostly Europe-based tech jobs."""
    try:
        resp = requests.get("https://www.arbeitnow.com/api/job-board-api", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        raw = resp.json().get("data", [])
    except Exception as e:
        print(f"[Arbeitnow] fetch failed: {e}")
        return []

    keywords_lower = [k.lower() for k in keywords]
    matched = []
    for job in raw:
        title = job.get("title", "")
        company = job.get("company_name", "")
        tags = " ".join(job.get("tags", []))
        if _matches(f"{title} {company} {tags}", keywords_lower):
            matched.append({
                "title": title or "Unknown role",
                "company": company or "Unknown company",
                "url": job.get("url", ""),
                "description": job.get("description", ""),
                "location": "Remote" if job.get("remote") else job.get("location", "Unknown"),
                "source": "Arbeitnow",
            })
        if len(matched) >= max_results:
            break
    return matched

def fetch_jobicy_jobs(keywords: List[str], max_results: int = 50) -> List[Dict]:
    """Free, no auth. Remote jobs, tech-leaning."""
    try:
        resp = requests.get(
            "https://jobicy.com/api/v2/remote-jobs",
            params={"count": 50},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[Jobicy] fetch failed: {e}")
        return []

    keywords_lower = [k.lower() for k in keywords]
    matched = []
    for job in raw:
        title = job.get("jobTitle", "")
        company = job.get("companyName", "")
        tags = " ".join(job.get("jobIndustry", []) if isinstance(job.get("jobIndustry"), list) else [])
        searchable = f"{title} {company} {tags}"
        if _matches(searchable, keywords_lower):
            matched.append({
                "title": title or "Unknown role",
                "company": company or "Unknown company",
                "url": job.get("url", ""),
                "description": job.get("jobExcerpt", job.get("jobDescription", "")),
                "location": "Remote",
                "source": "Jobicy",
            })
        if len(matched) >= max_results:
            break
    return matched


def fetch_findwork_jobs(keywords: List[str], max_results: int = 50) -> List[Dict]:
    """Free with registration. Tech-focused job listings."""
    api_key = os.getenv("FINDWORK_API_KEY")
    if not api_key:
        print("[Findwork] Skipped - FINDWORK_API_KEY not set in .env")
        return []

    matched = []
    for kw in keywords[:3]:
        try:
            resp = requests.get(
                "https://findwork.dev/api/jobs/",
                params={"search": kw},
                headers={**HEADERS, "Authorization": f"Token {api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            for job in resp.json().get("results", []):
                matched.append({
                    "title": job.get("role", "Unknown role"),
                    "company": job.get("company_name", "Unknown company"),
                    "url": job.get("url", ""),
                    "description": job.get("text", ""),
                    "location": "Remote" if job.get("remote") else job.get("location", "Unknown"),
                    "source": "Findwork",
                })
        except Exception as e:
            print(f"[Findwork] fetch failed for '{kw}': {e}")
        if len(matched) >= max_results:
            break
    return matched[:max_results]


def fetch_weworkremotely_jobs(keywords: List[str], max_results: int = 50) -> List[Dict]:
    """
    Free, no auth. WeWorkRemotely publishes an RSS feed specifically for
    syndication - this is a deliberately published feed, not scraping.
    """
    try:
        feed = feedparser.parse("https://weworkremotely.com/remote-jobs.rss")
    except Exception as e:
        print(f"[WeWorkRemotely] fetch failed: {e}")
        return []

    keywords_lower = [k.lower() for k in keywords]
    matched = []
    for entry in feed.entries:
        title_raw = entry.get("title", "")
        # WWR RSS titles are usually formatted "Company: Job Title"
        if ":" in title_raw:
            company, title = title_raw.split(":", 1)
        else:
            company, title = "Unknown company", title_raw

        description = entry.get("summary", "")
        # Match only on title+company, not description - WWR's RSS summary
        # field appears to contain boilerplate/category text shared across
        # many listings, which was causing false-positive matches on
        # clearly unrelated roles (e.g. "UX Designer" matching "AI Engineer").
        if _matches(f"{title} {company}", keywords_lower):
            matched.append({
                "title": title.strip() or "Unknown role",
                "company": company.strip() or "Unknown company",
                "url": entry.get("link", ""),
                "description": description,
                "location": "Remote",
                "source": "WeWorkRemotely",
            })
        if len(matched) >= max_results:
            break
    return matched
'''

# ---------- Key-based sources ----------
'''
def fetch_jooble_jobs(keywords: List[str], max_results: int = 50) -> List[Dict]:
    api_key = os.getenv("JOOBLE_API_KEY")
    if not api_key:
        print("[Jooble] Skipped - JOOBLE_API_KEY not set in .env")
        return []

    try:
        resp = requests.post(
            f"https://jooble.org/api/{api_key}",
            json={"keywords": " ".join(keywords[:2]), "location": ""},
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[Jooble] fetch failed: {e}")
        return []

    matched = []
    for job in raw[:max_results]:
        matched.append({
            "title": job.get("title", "Unknown role"),
            "company": job.get("company", "Unknown company"),
            "url": job.get("link", ""),
            "description": job.get("snippet", ""),
            "location": job.get("location", "Unknown"),
            "source": "Jooble",
        })
    return matched


def fetch_careerjet_jobs(keywords: List[str], max_results: int = 50) -> List[Dict]:
    affid = os.getenv("CAREERJET_AFFILIATE_ID")
    if not affid:
        print("[Careerjet] Skipped - CAREERJET_AFFILIATE_ID not set in .env")
        return []

    try:
        resp = requests.get(
            "http://public-api.careerjet.net/search",
            params={
                "keywords": " ".join(keywords[:2]),
                "locale_code": "en_GB",
                "affid": affid,
                "user_ip": "1.1.1.1",
                "user_agent": HEADERS["User-Agent"],
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[Careerjet] fetch failed: {e}")
        return []

    matched = []
    for job in raw[:max_results]:
        matched.append({
            "title": job.get("title", "Unknown role"),
            "company": job.get("company", "Unknown company"),
            "url": job.get("url", ""),
            "description": job.get("description", ""),
            "location": job.get("locations", "Unknown"),
            "source": "Careerjet",
        })
    return matched

'''
def _dedupe(jobs: List[Dict]) -> List[Dict]:
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
    Combines every configured source. Key-based sources (Jooble, Careerjet)
    silently skip themselves if not configured in .env, so this always
    works with at least the no-key sources even before you add API keys.
    """
    all_jobs = []
    all_jobs += fetch_remoteok_jobs(keywords, max_results=max_results)
    all_jobs += fetch_himalayas_jobs(keywords, max_results=max_results)
    #all_jobs += fetch_remotive_jobs(keywords, max_results=max_results)
    #all_jobs += fetch_arbeitnow_jobs(keywords, max_results=max_results)
    #all_jobs += fetch_weworkremotely_jobs(keywords, max_results=max_results)
    #all_jobs += fetch_jooble_jobs(keywords, max_results=max_results)
    #all_jobs += fetch_careerjet_jobs(keywords, max_results=max_results)
    #all_jobs += fetch_jobicy_jobs(keywords, max_results=max_results)
    #all_jobs += fetch_findwork_jobs(keywords, max_results=max_results)

    return _dedupe(all_jobs)[:max_results]


if __name__ == "__main__":
    test_keywords = ["Machine Learning", "NLP", "AI Engineer"]
    jobs = fetch_all_jobs(test_keywords, max_results=50)
    print(f"Found {len(jobs)} unique matching jobs across all sources\n")

    from collections import Counter
    by_source = Counter(job["source"] for job in jobs)
    print("Breakdown by source:", dict(by_source), "\n")

    for job in jobs[:20]:
        print(f"[{job['source']}] {job['title']} @ {job['company']} ({job['location']})")