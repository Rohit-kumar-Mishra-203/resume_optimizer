import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (personal resume tool; contact: you@example.com)"}
keywords_lower = ["machine learning", "nlp", "ai engineer"]

offset = 0
page_size = 20
total_scanned = 0

for page in range(5):
    resp = requests.get(
        "https://himalayas.app/jobs/api",
        params={"limit": page_size, "offset": offset},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    jobs = data.get("jobs", [])
    total_count = data.get("totalCount", 0)

    print(f"--- Page {page} (offset={offset}) --- totalCount={total_count}, jobs returned={len(jobs)}")

    for job in jobs:
        title = job.get("title", "")
        company = job.get("companyName", "")
        categories = " ".join(job.get("categories", []))
        searchable = f"{title} {company} {categories}".lower()
        is_match = any(kw in searchable for kw in keywords_lower)
        marker = "MATCH" if is_match else "     "
        print(f"  [{marker}] {title} @ {company} | categories: {categories[:80]}")

    total_scanned += len(jobs)
    offset += page_size
    if not jobs or offset >= total_count:
        print("Reached end of available jobs.")
        break

print(f"\nTotal jobs scanned: {total_scanned}")