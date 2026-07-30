from __future__ import annotations

from pathlib import Path
import os
import re


RUNTIME_DIRS = ("projects", "runs", "environments", "locks", "backups")
RUN_DIRS = ("configuration", "tasks", "artifacts", "logs", "reports", "temp", "cache")


def sanitize_runtime_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip(".-")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Runtime identifier is empty or unsafe.")
    return cleaned[:96]


def get_runtime_root() -> Path:
    return Path(os.getenv("HYDROLITE_RUNTIME_DIR", "~/.hydrolite/runtime")).expanduser().resolve()


def get_runtime_db_path() -> Path:
    return Path(os.getenv("HYDROLITE_RUNTIME_DB", get_runtime_root() / "hydrolite_runtime.sqlite3")).expanduser().resolve()


def get_project_runtime_dir(project_id: str) -> Path:
    return get_runtime_root() / "projects" / sanitize_runtime_identifier(project_id)


def get_run_dir(run_id: str) -> Path:
    return get_runtime_root() / "runs" / sanitize_runtime_identifier(run_id)


def get_task_dir(run_id: str, task_id: str) -> Path:
    return get_run_dir(run_id) / "tasks" / sanitize_runtime_identifier(task_id)


def get_run_log_dir(run_id: str) -> Path:
    return get_run_dir(run_id) / "logs"


def get_run_artifact_dir(run_id: str) -> Path:
    return get_run_dir(run_id) / "artifacts"


def get_run_temp_dir(run_id: str) -> Path:
    return get_run_dir(run_id) / "temp"


def validate_runtime_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    root = get_runtime_root()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path escapes runtime root: {candidate}")
    return candidate


def ensure_runtime_directories(run_id: str | None = None, task_id: str | None = None) -> dict[str, Path]:
    root = get_runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    paths = {"root": root}
    for name in RUNTIME_DIRS:
        paths[name] = root / name
        paths[name].mkdir(parents=True, exist_ok=True)
    if run_id:
        run = get_run_dir(run_id)
        run.mkdir(parents=True, exist_ok=True)
        paths["run"] = run
        for name in RUN_DIRS:
            paths[name] = run / name
            paths[name].mkdir(parents=True, exist_ok=True)
        if task_id:
            task = get_task_dir(run_id, task_id)
            for name in ("work",):
                (task / name).mkdir(parents=True, exist_ok=True)
            paths["task"] = task
    return paths
