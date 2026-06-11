from __future__ import annotations

from pathlib import Path
import importlib.util
import os
from typing import Any


def _streamlit_secrets_available() -> bool:
    try:
        import streamlit as st

        return bool(getattr(st, "secrets", {}))
    except Exception:
        return False


def detect_gee_credentials() -> dict[str, Any]:
    """Detect possible Earth Engine credential sources without logging in."""
    local_candidates = [
        Path.home() / ".config" / "earthengine" / "credentials",
        Path.home() / ".config" / "earthengine" / "legacy_credentials",
    ]
    local_credentials = [str(path) for path in local_candidates if path.exists()]
    service_account = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    project = os.environ.get("GEE_PROJECT", "")
    return {
        "earthengine_api_installed": importlib.util.find_spec("ee") is not None,
        "local_earthengine_credentials": local_credentials,
        "google_application_credentials": service_account,
        "google_application_credentials_exists": bool(service_account and Path(service_account).exists()),
        "streamlit_secrets_detected": _streamlit_secrets_available(),
        "gee_project": project,
        "credential_sources_detected": bool(local_credentials or service_account or _streamlit_secrets_available()),
    }


def initialize_gee(project: str | None = None) -> dict[str, Any]:
    """Try a non-interactive Earth Engine initialization.

    This intentionally does not call ee.Authenticate() or trigger browser login.
    """
    status = detect_gee_credentials()
    project_value = project or status.get("gee_project") or None
    if not status["earthengine_api_installed"]:
        return {
            "status": "unavailable",
            "project": project_value,
            "message": "earthengine-api is not installed.",
        }
    if not status["credential_sources_detected"]:
        return {
            "status": "unavailable",
            "project": project_value,
            "message": "No GEE credentials detected. Configure local credentials, GOOGLE_APPLICATION_CREDENTIALS, or Streamlit secrets.",
        }
    try:
        import ee

        if project_value:
            ee.Initialize(project=project_value)
        else:
            ee.Initialize()
        return {"status": "available", "project": project_value, "message": "Earth Engine initialized."}
    except Exception as exc:
        return {
            "status": "unavailable",
            "project": project_value,
            "message": f"Earth Engine initialization failed without interactive login: {exc}",
        }


def get_gee_status() -> dict[str, Any]:
    credentials = detect_gee_credentials()
    initialization = initialize_gee(project=credentials.get("gee_project") or None)
    return {"credentials": credentials, "initialization": initialization}
