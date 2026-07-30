from __future__ import annotations

from pathlib import Path
import json
import os
import socket
import sys

from hydrolite.runtime_db import get_database_version, initialize_runtime_database
from hydrolite.runtime_mode import detect_runtime_mode
from hydrolite.runtime_paths import get_runtime_root


ROOT = Path(__file__).resolve().parents[1]


def validate_streamlit_configuration() -> dict:
    config = ROOT / ".streamlit" / "config.toml"
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    errors = []
    if "headless" not in text: errors.append("server.headless is missing")
    return {"status": "passed" if not errors else "failed", "path": str(config), "errors": errors}


def validate_runtime_permissions() -> dict:
    root = get_runtime_root(); root.mkdir(parents=True, exist_ok=True)
    return {"status": "passed" if os.access(root, os.W_OK) else "failed", "runtime_root": str(root), "writable": os.access(root, os.W_OK)}


def validate_entrypoint() -> dict:
    path = ROOT / "streamlit_app.py"
    return {"status": "passed" if path.is_file() else "failed", "path": str(path)}


def diagnose_local_deployment() -> dict:
    initialize_runtime_database()
    return {"status": "passed", "mode": detect_runtime_mode("local_full"), "runtime": validate_runtime_permissions(), "entrypoint": validate_entrypoint(), "streamlit": validate_streamlit_configuration(), "database_version": get_database_version()}


def diagnose_streamlit_cloud_deployment() -> dict:
    mode = detect_runtime_mode("cloud_streamlit")
    blocked = all(not mode["capabilities"][key] for key in ("qgis", "hec_hms", "connector_download", "ml_training"))
    return {"status": "passed" if blocked and validate_entrypoint()["status"] == "passed" else "failed", "mode": mode, "local_backends_blocked": blocked, "entrypoint": validate_entrypoint()}


def build_deployment_manifest() -> dict:
    return {"local": diagnose_local_deployment(), "cloud": diagnose_streamlit_cloud_deployment(), "python": sys.version, "entrypoint": "streamlit_app.py"}


def write_deployment_report(output_dir: str | Path, result: dict) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    json_path = output / "deployment_diagnosis.json"
    md_path = output / "deployment_diagnosis.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(f"# Deployment Diagnosis\n\n- Local: `{result['local']['status']}`\n- Cloud: `{result['cloud']['status']}`\n- Entrypoint: `streamlit_app.py`\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
