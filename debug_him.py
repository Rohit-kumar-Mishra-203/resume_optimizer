import requests
import json

resp = requests.get(
    "https://himalayas.app/jobs/api",
    params={"limit": 5},
    headers={"User-Agent": "Mozilla/5.0 (personal resume tool; contact: you@example.com)"},
    timeout=15,
)
resp.raise_for_status()
data = resp.json()

print("Top-level keys:", list(data.keys()))
print()

jobs = data.get("jobs", data.get("data", []))
print(f"Number of jobs returned: {len(jobs)}")
print()

if jobs:
    print("First job's full structure:")
    print(json.dumps(jobs[0], indent=2))