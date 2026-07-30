from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json

from hydrolite.desktop.desktop_paths import get_application_support_dir, get_desktop_log_dir
from hydrolite.runtime_db import get_database_version
from hydrolite.runtime_recovery import recover_all_runtime


def _state_path() -> Path:
    return get_application_support_dir() / "desktop_state.json"


def record_desktop_start() -> Path:
    path = _state_path(); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"clean_shutdown": False, "started_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def record_clean_shutdown() -> Path:
    path = _state_path(); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"clean_shutdown": True, "finished_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def detect_unclean_shutdown() -> bool:
    path = _state_path()
    if not path.exists():
        return False
    try:
        return not bool(json.loads(path.read_text(encoding="utf-8")).get("clean_shutdown"))
    except (OSError, json.JSONDecodeError):
        return True


def recover_desktop_state() -> dict:
    unclean = detect_unclean_shutdown()
    recovery = recover_all_runtime() if unclean else {"status": "not_required"}
    return {"status": "recovered" if unclean else "clean", "unclean_shutdown": unclean, "runtime_recovery": recovery, "database_version": get_database_version()}


def collect_crash_diagnostics() -> dict:
    return {"unclean_shutdown": detect_unclean_shutdown(), "state_file": str(_state_path()), "log_dir": str(get_desktop_log_dir()), "database_version": get_database_version()}


def write_crash_report() -> Path:
    path = get_desktop_log_dir() / "desktop_crash_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(collect_crash_diagnostics(), indent=2), encoding="utf-8")
    return path


def clear_recovered_state() -> dict:
    return {"status": "cleared", "path": str(record_clean_shutdown())}
