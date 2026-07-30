#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "macos_packaging"


def _run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    return (result.stdout or result.stderr).strip()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    envs = json.loads(_run(["conda", "env", "list", "--json"]) or '{"envs": []}') if shutil.which("conda") else {"envs": []}
    env_path = next((item for item in envs["envs"] if item.endswith("/hydrolite-build")), "")
    python = str(Path(env_path) / "bin" / "python") if env_path else ""
    payload = {
        "status": "available" if python and Path(python).exists() else "missing",
        "environment_name": "hydrolite-build",
        "environment_python": python,
        "current_python": sys.version,
        "current_executable": sys.executable,
        "machine": platform.machine(),
        "macos": platform.mac_ver()[0],
        "conda": _run(["conda", "--version"]) if shutil.which("conda") else "missing",
        "swift": _run(["swift", "--version"]) if shutil.which("swift") else "missing",
        "xcode_select": _run(["xcode-select", "-p"]) if shutil.which("xcode-select") else "missing",
        "xcode": _run(["xcodebuild", "-version"]) if shutil.which("xcodebuild") else "Command Line Tools only",
        "pyinstaller": "",
        "streamlit": "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload["status"] == "available":
        versions = _run([python, "-c", "import importlib.metadata as m; print(m.version('pyinstaller')); print(m.version('streamlit'))"]).splitlines()
        payload["pyinstaller"] = versions[0] if versions else ""
        payload["streamlit"] = versions[1] if len(versions) > 1 else ""
    json_path, md_path = OUTPUT / "build_environment.json", OUTPUT / "build_environment.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "# macOS Build Environment\n\n"
        f"- Status: `{payload['status']}`\n- Environment: `hydrolite-build`\n"
        f"- Python: `{payload['environment_python'] or 'not created'}`\n"
        f"- PyInstaller: `{payload['pyinstaller'] or 'not installed'}`\n"
        f"- Swift: `{payload['swift'].splitlines()[0]}`\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
