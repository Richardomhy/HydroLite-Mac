from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys
import time

from hydrolite.desktop.desktop_health import check_desktop_health
from hydrolite.desktop.desktop_paths import ensure_desktop_directories
from hydrolite.desktop.port_manager import find_free_loopback_port, reject_non_loopback_address
from hydrolite.process_manager import inspect_managed_process, start_managed_process, terminate_managed_process, verify_process_stopped


def locate_streamlit_entrypoint() -> Path:
    candidates = []
    if os.getenv("HYDROLITE_BUNDLE_RESOURCES"):
        candidates.append(Path(os.environ["HYDROLITE_BUNDLE_RESOURCES"]) / "app" / "streamlit_app.py")
    if getattr(sys, "frozen", False):
        candidates.extend([Path(getattr(sys, "_MEIPASS")) / "streamlit_app.py", Path(getattr(sys, "_MEIPASS")) / "app" / "streamlit_app.py"])
    candidates.append(Path(__file__).resolve().parents[2] / "streamlit_app.py")
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("streamlit_app.py is missing from the desktop bundle")


def build_streamlit_command(port: int, runtime_dir: str | Path) -> list[str]:
    if not 0 < int(port) < 65536:
        raise ValueError("port must be between 1 and 65535")
    return [
        sys.executable, "-m", "streamlit", "run", str(locate_streamlit_entrypoint()),
        "--server.address", "127.0.0.1", "--server.port", str(int(port)),
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]


def build_streamlit_environment(runtime_dir: str | Path) -> dict[str, str]:
    root = Path(runtime_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return {
        "HYDROLITE_RUNTIME_DIR": str(root),
        "HYDROLITE_RUNTIME_DB": str(root / "hydrolite_runtime.sqlite3"),
        "HYDROLITE_RUNTIME_MODE": "local_full",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    }


def start_streamlit_backend(runtime_dir: str | Path | None = None, port: int | None = None) -> dict:
    paths = ensure_desktop_directories()
    runtime = Path(runtime_dir or Path.home() / ".hydrolite" / "runtime").expanduser().resolve()
    selected = int(port or find_free_loopback_port())
    reject_non_loopback_address("127.0.0.1")
    stdout, stderr = paths["logs"] / "backend.stdout.log", paths["logs"] / "backend.stderr.log"
    pid = start_managed_process(build_streamlit_command(selected, runtime), Path(__file__).resolve().parents[2], build_streamlit_environment(runtime), stdout, stderr)
    manifest = write_backend_manifest(paths["application_support"] / "backend_manifest.json", pid, selected, runtime)
    return {**manifest, "health": wait_for_backend_health(pid, selected)}


def wait_for_backend_health(process_id: int, port: int, timeout: float = 45) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        process = inspect_managed_process(process_id)
        if not process["running"]:
            return {"status": "failed", "message": "Backend exited before becoming healthy"}
        health = check_desktop_health(port, True)
        if health["status"] == "passed":
            return health
        time.sleep(0.25)
    return {"status": "failed", "message": f"Backend health timeout after {timeout} seconds"}


def stop_streamlit_backend(process_id: int) -> dict:
    stopped = terminate_managed_process(int(process_id))
    return {"status": "stopped" if stopped and verify_backend_stopped(process_id) else "failed", "process_id": int(process_id)}


def verify_backend_stopped(process_id: int) -> bool:
    return verify_process_stopped(int(process_id))


def write_backend_manifest(path: str | Path, process_id: int, port: int, runtime_dir: str | Path) -> dict:
    manifest = {
        "pid": int(process_id), "port": int(port), "address": "127.0.0.1",
        "url": f"http://127.0.0.1:{int(port)}", "runtime_dir": str(Path(runtime_dir).resolve()),
        "entrypoint": str(locate_streamlit_entrypoint()), "started_at": datetime.now(timezone.utc).isoformat(),
    }
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def collect_backend_diagnostics(manifest_path: str | Path) -> dict:
    path = Path(manifest_path)
    if not path.exists():
        return {"status": "missing", "manifest": str(path)}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    process = inspect_managed_process(int(manifest["pid"]))
    return {"status": "passed", "manifest": manifest, "process": process, "health": check_desktop_health(int(manifest["port"]), process["running"])}
