from __future__ import annotations

from pathlib import Path
import argparse
import atexit
import os
import signal
import sys

from hydrolite.desktop.backend import build_streamlit_environment, locate_streamlit_entrypoint, write_backend_manifest
from hydrolite.desktop.crash_recovery import record_clean_shutdown, record_desktop_start, recover_desktop_state
from hydrolite.desktop.desktop_paths import ensure_desktop_directories
from hydrolite.desktop.port_manager import find_free_loopback_port
from hydrolite.desktop.single_instance import acquire_application_lock, focus_existing_instance, release_application_lock
from hydrolite.runtime_db import initialize_runtime_database


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="HydroLite Studio packaged Streamlit backend")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--runtime-dir", default=str(Path.home() / ".hydrolite" / "runtime"))
    parser.add_argument("--manifest")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = ensure_desktop_directories()
    lock = acquire_application_lock()
    if lock["status"] != "acquired":
        focus_existing_instance()
        return 73
    atexit.register(release_application_lock)
    record_desktop_start()
    atexit.register(record_clean_shutdown)
    recover_desktop_state()
    runtime = Path(args.runtime_dir).expanduser().resolve()
    os.environ.update(build_streamlit_environment(runtime))
    initialize_runtime_database()
    port = args.port or find_free_loopback_port()
    manifest_path = Path(args.manifest or paths["application_support"] / "backend_manifest.json")
    write_backend_manifest(manifest_path, os.getpid(), port, runtime)
    signal.signal(signal.SIGTERM, lambda *_: raise_system_exit())
    from streamlit.web import cli as streamlit_cli
    sys.argv = [
        "streamlit", "run", str(locate_streamlit_entrypoint()),
        "--server.address", "127.0.0.1", "--server.port", str(port),
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    return int(streamlit_cli.main() or 0)


def raise_system_exit() -> None:
    raise SystemExit(0)


if __name__ == "__main__":
    raise SystemExit(main())
