from __future__ import annotations

from pathlib import Path
import importlib.util
import os
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_CONFIG = PROJECT_ROOT / "configs" / "gee.local.yaml"


def _earthengine_credentials_exist() -> bool:
    return any(
        path.exists()
        for path in (
            Path.home() / ".config" / "earthengine" / "credentials",
            Path.home() / ".config" / "earthengine" / "legacy_credentials",
        )
    )


def _streamlit_gee_project() -> str:
    try:
        import streamlit as st

        gee = st.secrets.get("gee", {})
        if isinstance(gee, dict):
            return str(gee.get("project", "") or "")
    except Exception:
        return ""
    return ""


def _local_config_project() -> str:
    if not LOCAL_CONFIG.exists():
        return ""
    try:
        data = yaml.safe_load(LOCAL_CONFIG.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("project", "") or "")


def _resolve_project(explicit_project: str | None = None) -> tuple[str | None, str]:
    candidates = [
        ("argument", explicit_project or ""),
        ("GEE_PROJECT", os.environ.get("GEE_PROJECT", "")),
        ("GOOGLE_CLOUD_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", "")),
        ("streamlit_secrets.gee.project", _streamlit_gee_project()),
        ("configs/gee.local.yaml", _local_config_project()),
    ]
    for source, value in candidates:
        if value:
            return value, source
    return None, ""


def detect_gee_credentials() -> dict[str, Any]:
    """Detect Earth Engine credential sources without copying or printing secrets."""
    service_account = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    streamlit_project = _streamlit_gee_project()
    local_project = _local_config_project()
    project, project_source = _resolve_project()
    sources = []
    if _earthengine_credentials_exist():
        sources.append("local_earthengine_credentials")
    if service_account:
        sources.append("GOOGLE_APPLICATION_CREDENTIALS")
    if streamlit_project:
        sources.append("streamlit_secrets.gee.project")
    if local_project:
        sources.append("configs/gee.local.yaml")
    return {
        "earthengine_api_installed": importlib.util.find_spec("ee") is not None,
        "local_earthengine_credentials_detected": _earthengine_credentials_exist(),
        "google_application_credentials_detected": bool(service_account),
        "google_application_credentials_file_exists": bool(service_account and Path(service_account).exists()),
        "streamlit_secrets_detected": bool(streamlit_project),
        "gee_local_config_detected": LOCAL_CONFIG.exists(),
        "gee_project": project or "",
        "gee_project_source": project_source,
        "auth_sources_detected": sources,
        "credential_sources_detected": bool(sources),
    }


def initialize_gee(project: str | None = None) -> dict[str, Any]:
    """Initialize Earth Engine non-interactively when credentials are already available."""
    credentials = detect_gee_credentials()
    project_value, project_source = _resolve_project(project)
    next_steps = [
        "Install earthengine-api if it is missing: python -m pip install earthengine-api",
        "Authenticate locally without committing credentials: python scripts/gee_auth_local.py",
        "Set a project: export GEE_PROJECT=\"your-gee-project-id\"",
        "For Streamlit Cloud, configure secrets as [gee] project = \"your-gee-project-id\".",
    ]
    if not credentials["earthengine_api_installed"]:
        return {
            "status": "unavailable",
            "project": project_value,
            "auth_source": "",
            "error_message": "earthengine-api is not installed.",
            "next_steps": next_steps,
        }
    if not credentials["credential_sources_detected"]:
        return {
            "status": "unavailable",
            "project": project_value,
            "auth_source": "",
            "error_message": "No Earth Engine credentials detected.",
            "next_steps": next_steps,
        }
    try:
        import ee

        if project_value:
            ee.Initialize(project=project_value)
        else:
            ee.Initialize()
        return {
            "status": "available",
            "project": project_value,
            "auth_source": project_source or ", ".join(credentials["auth_sources_detected"]),
            "error_message": "",
            "next_steps": [],
        }
    except Exception as exc:
        return {
            "status": "failed",
            "project": project_value,
            "auth_source": project_source or ", ".join(credentials["auth_sources_detected"]),
            "error_message": str(exc),
            "next_steps": next_steps,
        }


def get_gee_status() -> dict[str, Any]:
    return {
        "credentials": detect_gee_credentials(),
        "initialization": initialize_gee(),
    }
