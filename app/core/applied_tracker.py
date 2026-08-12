import json
from pathlib import Path
from datetime import date
from typing import Dict, List, Optional

APPLIED_PATH = Path("data/applied_jobs.json")

VALID_STATUSES = ["applied", "interview_scheduled", "rejected", "no_response", "offer"]


def _load() -> Dict:
    if APPLIED_PATH.exists():
        return json.loads(APPLIED_PATH.read_text(encoding="utf-8"))
    return {}


def _save(data: Dict) -> None:
    APPLIED_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPLIED_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _key(title: str, company: str) -> str:
    return f"{title.strip().lower()}::{company.strip().lower()}"


def mark_applied(title: str, company: str, url: str = "", source: str = "", ats_score: Optional[float] = None) -> None:
    data = _load()
    data[_key(title, company)] = {
        "title": title,
        "company": company,
        "url": url,
        "source": source,
        "ats_score": ats_score,
        "date_applied": date.today().isoformat(),
        "status": "applied",
        "status_updated": date.today().isoformat(),
        "notes": "",
    }
    _save(data)


def unmark_applied(title: str, company: str) -> None:
    data = _load()
    data.pop(_key(title, company), None)
    _save(data)


def update_status(title: str, company: str, status: str, notes: str = "") -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    data = _load()
    key = _key(title, company)
    if key in data:
        data[key]["status"] = status
        data[key]["status_updated"] = date.today().isoformat()
        if notes:
            data[key]["notes"] = notes
        _save(data)


def is_applied(title: str, company: str) -> bool:
    return _key(title, company) in _load()


def get_applied_jobs() -> List[Dict]:
    data = _load()
    jobs = list(data.values())
    jobs.sort(key=lambda j: j["date_applied"], reverse=True)
    return jobs


def get_experiment_summary(days: int = 30) -> Dict:
    """
    Summarizes your personal experiment: how many jobs were applied to,
    how many led to interviews, over the given window.
    """
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    jobs = get_applied_jobs()
    recent = [j for j in jobs if j["date_applied"] >= cutoff]

    interviews = [j for j in recent if j["status"] in ("interview_scheduled", "offer")]
    rejected = [j for j in recent if j["status"] == "rejected"]
    no_response = [j for j in recent if j["status"] == "no_response"]
    pending = [j for j in recent if j["status"] == "applied"]

    return {
        "window_days": days,
        "total_applied": len(recent),
        "interviews": len(interviews),
        "rejected": len(rejected),
        "no_response": len(no_response),
        "still_pending": len(pending),
        "response_rate": round(
            (len(interviews) + len(rejected)) / len(recent) * 100, 1
        ) if recent else 0,
    }