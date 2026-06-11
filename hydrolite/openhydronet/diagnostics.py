from __future__ import annotations

import importlib.util
import os
import platform
import sys
from typing import Any

from hydrolite.openhydronet.runner import detect_openhydronet_environment


def _mps_available() -> bool:
    try:
        import torch

        return bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    except Exception:
        return False


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def build_openhydronet_diagnosis() -> dict[str, Any]:
    env = detect_openhydronet_environment()
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "torch_installed": env["torch_installed"],
        "can_import_googlehydrology": importlib.util.find_spec("googlehydrology") is not None,
        "openhydronet_home": os.environ.get("OPENHYDRONET_HOME", ""),
        "openhydronet_home_exists": env["openhydronet_home_exists"],
        "gpu_cuda_available": _cuda_available(),
        "mps_available": _mps_available(),
        "status": "placeholder_only",
        "message": "This diagnosis does not run real OpenHydroNet training or inference.",
    }
