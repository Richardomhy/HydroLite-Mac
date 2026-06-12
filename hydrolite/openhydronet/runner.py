from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import os
import platform
import subprocess
from typing import Any

import pandas as pd

from hydrolite.openhydronet.adapter import prepare_openhydronet_inputs
from hydrolite.openhydronet.config import load_openhydronet_config, validate_openhydronet_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_openhydronet_repo_path() -> Path:
    return PROJECT_ROOT / "external" / "openhydronet" / "flood-forecasting"


def resolve_openhydronet_home(config: dict[str, Any] | None = None) -> Path:
    configured = ""
    if config:
        configured = str(config.get("openhydronet_home") or "")
    value = os.environ.get("OPENHYDRONET_HOME") or configured
    return Path(value).expanduser() if value else default_openhydronet_repo_path()


def _torch_status() -> dict[str, Any]:
    if importlib.util.find_spec("torch") is None:
        return {
            "installed": False,
            "version": "",
            "mps_available": False,
            "cuda_available": False,
            "accelerator": "CPU",
            "error_message": "torch is not installed in the current Python environment.",
        }


def _conda_base() -> str:
    try:
        completed = subprocess.run(["conda", "info", "--base"], capture_output=True, text=True, check=False, timeout=10)
        return completed.stdout.strip() if completed.returncode == 0 else ""
    except Exception:
        return ""


def find_isolated_openhydronet_python() -> str:
    configured = os.environ.get("OPENHYDRONET_PYTHON", "")
    candidates = [configured] if configured else []
    conda_base = _conda_base()
    if conda_base:
        candidates.append(str(Path(conda_base) / "envs" / "hydrolite-openhydronet" / "bin" / "python"))
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.exists():
            return str(path)
    return ""


def _isolated_torch_status(python_path: str) -> dict[str, Any]:
    if not python_path:
        return {"available": False, "python": "", "torch_installed": False, "accelerator": "CPU"}
    code = (
        "import json\n"
        "try:\n"
        " import torch\n"
        " mps=bool(getattr(torch.backends,'mps',None) and torch.backends.mps.is_available())\n"
        " cuda=bool(torch.cuda.is_available())\n"
        " print(json.dumps({'available': True, 'python': __import__('sys').executable, "
        "'torch_installed': True, 'torch_version': getattr(torch,'__version__',''), "
        "'mps_available': mps, 'cuda_available': cuda, "
        "'accelerator': 'CUDA' if cuda else 'MPS' if mps else 'CPU'}))\n"
        "except Exception as exc:\n"
        " print(json.dumps({'available': True, 'python': __import__('sys').executable, "
        "'torch_installed': False, 'torch_version': '', 'mps_available': False, "
        "'cuda_available': False, 'accelerator': 'CPU', 'error_message': str(exc)}))\n"
    )
    try:
        completed = subprocess.run([python_path, "-c", code], capture_output=True, text=True, check=False, timeout=20)
        if completed.returncode == 0 and completed.stdout.strip():
            return json.loads(completed.stdout.strip().splitlines()[-1])
        return {
            "available": True,
            "python": python_path,
            "torch_installed": False,
            "accelerator": "CPU",
            "error_message": completed.stderr.strip() or f"return_code={completed.returncode}",
        }
    except Exception as exc:
        return {"available": True, "python": python_path, "torch_installed": False, "accelerator": "CPU", "error_message": str(exc)}
    try:
        import torch

        mps = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        cuda = bool(torch.cuda.is_available())
        accelerator = "CUDA" if cuda else "MPS" if mps else "CPU"
        return {
            "installed": True,
            "version": getattr(torch, "__version__", ""),
            "mps_available": mps,
            "cuda_available": cuda,
            "accelerator": accelerator,
            "error_message": "",
        }
    except Exception as exc:
        return {
            "installed": False,
            "version": "",
            "mps_available": False,
            "cuda_available": False,
            "accelerator": "CPU",
            "error_message": str(exc),
        }


def detect_openhydronet_environment() -> dict[str, Any]:
    home = os.environ.get("OPENHYDRONET_HOME", "")
    repo_path = Path(home).expanduser() if home else default_openhydronet_repo_path()
    torch_status = _torch_status()
    isolated_python = find_isolated_openhydronet_python()
    isolated_status = _isolated_torch_status(isolated_python)
    accelerator = torch_status["accelerator"]
    if accelerator == "CPU" and isolated_status.get("torch_installed"):
        accelerator = str(isolated_status.get("accelerator") or "CPU")
    readme_exists = any((repo_path / name).exists() for name in ("README.md", "README.rst", "README"))
    requirements_path = repo_path / "requirements.txt"
    repo_exists = repo_path.exists()
    can_import_googlehydrology = importlib.util.find_spec("googlehydrology") is not None
    if repo_exists and readme_exists:
        status = "available"
        error_message = ""
        next_steps = "Run the smoke test. Real training and large inference remain disabled in this phase."
    else:
        status = "unavailable"
        error_message = f"OpenHydroNet repository not found or incomplete at {repo_path}."
        next_steps = "Run scripts/openhydronet_env/clone_openhydronet_repo.sh and then create the isolated environment."
    return {
        "openhydronet_home": home,
        "openhydronet_home_exists": bool(home and Path(home).exists()),
        "repo_path": str(repo_path),
        "repo_exists": repo_exists,
        "readme_exists": readme_exists,
        "requirements_exists": requirements_path.exists(),
        "torch_installed": torch_status["installed"],
        "torch_status": torch_status,
        "isolated_python": isolated_python,
        "isolated_torch_status": isolated_status,
        "googlehydrology_installed": can_import_googlehydrology,
        "machine": platform.machine(),
        "accelerator": accelerator,
        "environment": {
            "python_executable": os.sys.executable,
            "python_version": os.sys.version,
            "platform": platform.platform(),
        },
        "status": status,
        "error_message": error_message,
        "next_steps": next_steps,
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


def run_openhydronet_smoke(config_path: str | Path) -> dict[str, Any]:
    config = load_openhydronet_config(config_path)
    validation = validate_openhydronet_config(config)
    environment = detect_openhydronet_environment()
    output_dir = Path(config.get("output", {}).get("folder") or "output/openhydronet")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "smoke_test_summary.xlsx"
    report_path = output_dir / "smoke_test_report.md"
    repo = resolve_openhydronet_home(config)
    status = "skipped"
    message = "Smoke test did not run real model training, data download, or prediction."
    if validation["status"] == "failed":
        status = "failed"
        message = validation["message"]
    elif not repo.exists():
        status = "unavailable"
        message = f"External repository path does not exist: {repo}"
    elif environment["status"] == "available":
        status = "passed"

    row = {
        "status": status,
        "config_path": str(config_path),
        "config_validation_status": validation["status"],
        "missing_config_fields": ", ".join(validation.get("missing", [])),
        "openhydronet_home": os.environ.get("OPENHYDRONET_HOME", ""),
        "repo_path": str(repo),
        "repo_exists": repo.exists(),
        "readme_exists": environment.get("readme_exists", False),
        "requirements_exists": environment.get("requirements_exists", False),
        "torch_installed": environment.get("torch_installed", False),
        "torch_version": environment.get("torch_status", {}).get("version", ""),
        "accelerator": environment.get("accelerator", "CPU"),
        "training_run": False,
        "large_inference_run": False,
        "message": message,
    }
    pd.DataFrame([row]).to_excel(summary_path, index=False)
    report_path.write_text(
        "\n".join(
            [
                "# OpenHydroNet Smoke Test Report",
                "",
                f"Status: `{status}`",
                f"Config: `{config_path}`",
                f"Repository: `{repo}`",
                f"Accelerator: `{row['accelerator']}`",
                "",
                "This smoke test only checks configuration, repository visibility, and lightweight environment state.",
                "It does not train a model, download large data, or run real flood prediction.",
                "",
                f"Message: {message}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "status": status,
        "summary_path": summary_path,
        "report_path": report_path,
        "environment": environment,
        "message": message,
    }


def run_openhydronet_prepare_inputs(config_path: str | Path) -> dict[str, Any]:
    return prepare_openhydronet_inputs(config_path)
