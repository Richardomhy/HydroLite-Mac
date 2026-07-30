from __future__ import annotations

from pathlib import Path
import json
import platform
import shutil
import subprocess
import sys

from hydrolite.desktop.bundle_resources import validate_bundle_resources
from hydrolite.desktop.desktop_paths import detect_legacy_runtime, ensure_desktop_directories
from hydrolite.desktop.desktop_update import inspect_update_status
from hydrolite.desktop.signing_audit import audit_macos_signature, detect_developer_identities
from hydrolite.runtime_db import get_database_version


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_APP = ROOT / "dist" / "macos" / "HydroLite-Studio-0.7.0-arm64.app"


def build_desktop_diagnosis(app_path: str | Path | None = None) -> dict:
    paths = ensure_desktop_directories()
    app = Path(app_path or DEFAULT_APP)
    swift = subprocess.run(["swift", "--version"], capture_output=True, text=True, check=False, timeout=10)
    xcode = subprocess.run(["xcodebuild", "-version"], capture_output=True, text=True, check=False, timeout=10) if shutil.which("xcodebuild") else None
    signing = audit_macos_signature(app) if app.exists() else {"status": "missing", "signing_mode": "unsigned"}
    return {
        "status": "passed",
        "platform": platform.platform(), "architecture": platform.machine(),
        "python": {"version": sys.version, "executable": sys.executable},
        "swift": (swift.stdout or swift.stderr).strip(),
        "xcode": (xcode.stdout or xcode.stderr).strip() if xcode else "Command Line Tools only",
        "app_bundle": {"path": str(app), "exists": app.exists()},
        "resources": validate_bundle_resources(app / "Contents" / "Resources" / "backend" / "hydrolite-backend") if app.exists() else {"status": "missing"},
        "directories": {key: str(value) for key, value in paths.items()},
        "runtime_database_version": get_database_version(),
        "legacy_runtime": detect_legacy_runtime(),
        "developer_identities": detect_developer_identities(),
        "signing": signing,
        "updates": inspect_update_status(ROOT / "packaging" / "macos" / "update_config.example.json"),
    }


def write_desktop_diagnosis(
    output_dir: str | Path | None = None,
    app_path: str | Path | None = None,
    result: dict | None = None,
) -> dict[str, Path]:
    result = result or build_desktop_diagnosis(app_path)
    output = Path(output_dir) if output_dir else ensure_desktop_directories()["logs"]
    output.mkdir(parents=True, exist_ok=True)
    json_path, md_path = output / "desktop_diagnosis.json", output / "desktop_diagnosis.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(f"# HydroLite Studio Desktop Diagnosis\n\n- Status: `{result['status']}`\n- Architecture: `{result['architecture']}`\n- App: `{result['app_bundle']['path']}`\n- Signing: `{result['signing']['signing_mode']}`\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
