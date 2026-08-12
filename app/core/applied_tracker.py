import json
from pathlib import Path
from datetime import date
from typing import Dict, List, Optional

APPLIED_PATH = Path("data/applied_jobs.json")


def _load() -> Dict:
    if APPLIED_PATH.exists():
        return json.loads(APPLIED_PATH.read_text(encoding="utf-8"))
    return {}


def _save(data: Dict) -> None:
    APPLIED_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPLIED_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _key(title: str, company: str) -> str:
    return f"{title.strip().lower()}::{company.strip().lower()}"


def mark_applied(title: str, company: str, url: str = "", source: str = "") -> None:
    data = _load()
    data[_key(title, company)] = {
        "title": title,
        "company": company,
        "url": url,
        "source": source,
        "date_applied": date.today().isoformat(),
    }
    _save(data)


def unmark_applied(title: str, company: str) -> None:
    data = _load()
    data.pop(_key(title, company), None)
    _save(data)


def is_applied(title: str, company: str) -> bool:
    return _key(title, company) in _load()


def get_applied_jobs() -> List[Dict]:
    data = _load()
    jobs = list(data.values())
    jobs.sort(key=lambda j: j["date_applied"], reverse=True)
    return jobs