from pathlib import Path

USERS_DIR = Path("data/users")


def user_dir(user_id: str) -> Path:
    d = USERS_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def resume_facts_path(user_id: str) -> Path:
    return user_dir(user_id) / "resume_facts.json"


def base_resume_path(user_id: str) -> Path:
    return user_dir(user_id) / "base_resume.tex"


def generated_dir(user_id: str) -> Path:
    d = user_dir(user_id) / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def checkpoint_path(user_id: str) -> Path:
    return user_dir(user_id) / "discovery_checkpoint.json"


def current_run_path(user_id: str) -> Path:
    return user_dir(user_id) / "current_run_results.json"


def status_path(user_id: str) -> Path:
    return user_dir(user_id) / "discovery_status.json"


def applied_jobs_path(user_id: str) -> Path:
    return user_dir(user_id) / "applied_jobs.json"