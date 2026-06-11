from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
import sys
from typing import Any

from hydrolite.gee.auth import detect_gee_credentials, initialize_gee


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def build_gee_diagnosis() -> dict[str, Any]:
    credentials = detect_gee_credentials()
    init = initialize_gee(project=os.environ.get("GEE_PROJECT") or None)
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "earthengine_api_version": _version("earthengine-api"),
        "geemap_version": _version("geemap"),
        "can_import_ee": importlib.util.find_spec("ee") is not None,
        "gee_project_detected": bool(os.environ.get("GEE_PROJECT")),
        "google_application_credentials_detected": bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
        "streamlit_secrets_detected": credentials["streamlit_secrets_detected"],
        "gee_initialization_status": init["status"],
        "gee_initialization_message": init["message"],
    }
