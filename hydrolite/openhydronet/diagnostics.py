from __future__ import annotations

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
        "status": env["status"],
        "environment": env["environment"],
        "repo_path": env["repo_path"],
        "torch_installed": env["torch_installed"],
        "torch_status": env["torch_status"],
        "isolated_python": env.get("isolated_python", ""),
        "isolated_torch_status": env.get("isolated_torch_status", {}),
        "accelerator": env["accelerator"],
        "can_import_googlehydrology": env["googlehydrology_installed"],
        "openhydronet_home": os.environ.get("OPENHYDRONET_HOME", ""),
        "openhydronet_home_exists": env["openhydronet_home_exists"],
        "repo_exists": env["repo_exists"],
        "readme_exists": env["readme_exists"],
        "requirements_exists": env["requirements_exists"],
        "gpu_cuda_available": _cuda_available(),
        "mps_available": _mps_available(),
        "error_message": env["error_message"],
        "next_steps": env["next_steps"],
        "message": "This diagnosis does not run real OpenHydroNet training or inference.",
    }
