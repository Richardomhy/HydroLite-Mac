from __future__ import annotations

from pathlib import Path
import os
import shutil
import tempfile


MODES = {"local_full", "local_light", "cloud_streamlit", "test", "read_only"}


def _writable() -> bool:
    try:
        with tempfile.NamedTemporaryFile():
            return True
    except OSError:
        return False


def detect_runtime_mode(preferred: str | None = None) -> dict:
    if preferred and preferred not in MODES:
        raise ValueError(f"Unsupported runtime mode: {preferred}")
    cloud = bool(os.getenv("STREAMLIT_SHARING_MODE") or os.getenv("STREAMLIT_CLOUD"))
    mode = preferred or os.getenv("HYDROLITE_RUNTIME_MODE") or ("cloud_streamlit" if cloud else "local_full")
    qgis = bool(shutil.which("qgis_process") or Path("/Applications/QGIS.app").exists())
    hms = Path("/Applications/HEC-HMS-4.13.app").exists()
    capabilities = {
        "write_files": _writable() and mode != "read_only",
        "subprocess": mode in {"local_full", "local_light", "test"},
        "qgis": mode == "local_full" and qgis,
        "hec_hms": mode == "local_full" and hms,
        "connector_download": mode == "local_full",
        "ml_training": False,
        "light_hydrology": mode != "read_only",
    }
    return {"mode": mode, "is_cloud": cloud, "qgis_detected": qgis, "hec_hms_detected": hms, "capabilities": capabilities}


def validate_task_for_mode(task: dict, mode: dict | None = None) -> dict:
    mode = mode or detect_runtime_mode()
    if mode["mode"] == "read_only":
        return {"status": "blocked", "reason": "read_only mode does not start tasks"}
    if task.get("local_only") and mode["mode"] == "cloud_streamlit":
        return {"status": "blocked", "reason": "Task is local-only and unavailable on Streamlit Cloud"}
    if not task.get("cloud_supported", True) and mode["mode"] == "cloud_streamlit":
        return {"status": "blocked", "reason": "Task is not supported in cloud mode"}
    return {"status": "passed", "reason": ""}
