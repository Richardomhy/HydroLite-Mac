from __future__ import annotations

from pathlib import Path
import importlib.util
import os
import platform
from typing import Any

from hydrolite.openhydronet.config import load_openhydronet_config, validate_openhydronet_config


def detect_openhydronet_environment() -> dict[str, Any]:
    home = os.environ.get("OPENHYDRONET_HOME", "")
    return {
        "openhydronet_home": home,
        "openhydronet_home_exists": bool(home and Path(home).exists()),
        "torch_installed": importlib.util.find_spec("torch") is not None,
        "googlehydrology_installed": importlib.util.find_spec("googlehydrology") is not None,
        "machine": platform.machine(),
        "status": "placeholder_ready",
    }


def explain_missing_environment() -> str:
    return (
        "OpenHydroNet is configured as a placeholder. Set OPENHYDRONET_HOME to an external "
        "checkout and install model dependencies in an isolated environment before real inference."
    )


def run_openhydronet_placeholder(config_path: str | Path) -> dict[str, Any]:
    config = load_openhydronet_config(config_path)
    validation = validate_openhydronet_config(config)
    environment = detect_openhydronet_environment()
    return {
        "status": "placeholder",
        "config_validation": validation,
        "environment": environment,
        "message": "No model training or inference was run.",
    }
