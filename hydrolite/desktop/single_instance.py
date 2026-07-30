from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import time

from hydrolite.desktop.desktop_paths import get_application_support_dir


def _default_lock() -> Path:
    return get_application_support_dir() / "desktop_instance.lock"


def _process_started(pid: int) -> str:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True, check=False, timeout=5)
    return result.stdout.strip()


def inspect_existing_instance(lock_path: str | Path | None = None) -> dict:
    path = Path(lock_path or _default_lock())
    if not path.exists():
        return {"status": "missing", "running": False, "lock_path": str(path)}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        pid = int(record["pid"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return {"status": "stale", "running": False, "lock_path": str(path)}
    started = _process_started(pid)
    running = bool(started and started == record.get("process_started"))
    return {**record, "status": "running" if running else "stale", "running": running, "lock_path": str(path)}


def detect_stale_lock(lock_path: str | Path | None = None) -> bool:
    return inspect_existing_instance(lock_path)["status"] == "stale"


def recover_stale_lock(lock_path: str | Path | None = None) -> dict:
    path = Path(lock_path or _default_lock())
    if path.exists() and detect_stale_lock(path):
        path.unlink()
        return {"status": "recovered", "lock_path": str(path)}
    return {"status": "unchanged", "lock_path": str(path)}


def acquire_application_lock(lock_path: str | Path | None = None) -> dict:
    path = Path(lock_path or _default_lock())
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = inspect_existing_instance(path)
    if existing["running"]:
        return {**existing, "status": "already_running"}
    recover_stale_lock(path)
    record = {"pid": os.getpid(), "process_started": _process_started(os.getpid()), "created_at": time.time()}
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
    return {"status": "acquired", "lock_path": str(path), **record}


def release_application_lock(lock_path: str | Path | None = None) -> dict:
    path = Path(lock_path or _default_lock())
    existing = inspect_existing_instance(path)
    if path.exists() and (existing.get("pid") == os.getpid() or not existing["running"]):
        path.unlink()
        return {"status": "released", "lock_path": str(path)}
    return {"status": "not_owner", "lock_path": str(path)}


def focus_existing_instance() -> dict:
    result = subprocess.run(["open", "-a", "HydroLite Studio"], capture_output=True, text=True, check=False, timeout=10)
    return {"status": "requested" if result.returncode == 0 else "unavailable", "error": result.stderr.strip()}


def write_instance_manifest(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inspect_existing_instance(), indent=2), encoding="utf-8")
    return path
