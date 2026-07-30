from __future__ import annotations

from pathlib import Path
import json
import os

from hydrolite.runtime_paths import get_runtime_root


DEFAULTS = {
    "runtime_directory": str(get_runtime_root()),
    "default_workspace_directory": str(Path("workspaces").resolve()),
    "output_directory": str(Path("output").resolve()),
    "max_parallel_tasks": 1,
    "default_task_timeout": 300,
    "preferred_language": "zh",
    "runtime_mode": "local_full",
    "enable_qgis": True,
    "enable_hec_hms": True,
    "enable_connectors": True,
    "enable_ml": False,
    "log_level": "INFO",
    "retain_temporary_files": False,
    "artifact_retention_days": 30,
}


def get_settings_path() -> Path:
    return Path(os.getenv("HYDROLITE_SETTINGS", "~/.hydrolite/settings.json")).expanduser().resolve()


def validate_settings(settings: dict) -> dict:
    errors = []
    if int(settings.get("max_parallel_tasks", 1)) not in {1, 2}:
        errors.append("max_parallel_tasks must be 1 or 2")
    if int(settings.get("default_task_timeout", 0)) <= 0:
        errors.append("default_task_timeout must be positive")
    if settings.get("runtime_mode") not in {"local_full", "local_light", "cloud_streamlit", "test", "read_only"}:
        errors.append("runtime_mode is invalid")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def load_settings() -> dict:
    path = get_settings_path()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        settings = {**DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError, TypeError):
        return dict(DEFAULTS)
    return settings if validate_settings(settings)["status"] == "passed" else dict(DEFAULTS)


def save_settings(settings: dict) -> Path:
    safe = {**DEFAULTS, **settings}
    for key in list(safe):
        if any(fragment in key.lower() for fragment in ("token", "password", "secret", "credential", "api_key")):
            safe.pop(key)
    validation = validate_settings(safe)
    if validation["status"] != "passed":
        raise ValueError("; ".join(validation["errors"]))
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def reset_settings() -> dict:
    path = get_settings_path()
    if path.exists():
        path.unlink()
    return dict(DEFAULTS)
