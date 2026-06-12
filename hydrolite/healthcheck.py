from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any

import pandas as pd

from hydrolite.__version__ import __app_name__, __release_date__, __version__
from hydrolite.gee.auth import get_gee_status
from hydrolite.openhydronet.runner import detect_openhydronet_environment
from hydrolite.swmm.runner import find_external_solver_python


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = (".pt", ".pth", ".ckpt", ".onnx")
FORBIDDEN_PATTERNS = ("secrets.toml", "credentials", "service-account", "external/openhydronet/flood-forecasting")


@dataclass(frozen=True)
class HealthcheckOutputs:
    output_dir: Path
    report_md: Path
    summary_xlsx: Path
    checks: pd.DataFrame


def _git_ignored(path: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return completed.returncode == 0
    except Exception:
        return False


def _tracked_files() -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return completed.stdout.splitlines() if completed.returncode == 0 else []
    except Exception:
        return []


def _add(rows: list[dict[str, Any]], check: str, status: str, message: str, severity: str = "info") -> None:
    rows.append({"check": check, "status": status, "severity": severity, "message": message})


def build_healthcheck() -> HealthcheckOutputs:
    rows: list[dict[str, Any]] = []
    _add(rows, "app_name", "passed", __app_name__)
    _add(rows, "version", "passed", __version__)
    _add(rows, "release_date", "passed", __release_date__)
    _add(rows, "python_version", "passed", sys.version.split()[0])
    _add(rows, "project_root", "passed", str(PROJECT_ROOT))

    for relative in ("requirements.txt", "streamlit_app.py", "projects/demo_project", "cases", "output", "data_raw"):
        path = PROJECT_ROOT / relative
        _add(rows, relative, "passed" if path.exists() else "failed", str(path), "fatal" if not path.exists() else "info")

    gee = get_gee_status()
    gee_status = str((gee.get("initialization") or {}).get("status", "unknown")) if isinstance(gee, dict) else "unknown"
    _add(rows, "gee_status", "passed" if gee_status == "available" else "warning", gee_status, "warning" if gee_status != "available" else "info")

    swmm_python = find_external_solver_python()
    _add(
        rows,
        "swmm_status",
        "passed" if swmm_python else "warning",
        str(swmm_python) if swmm_python else "No external SWMM solver detected; current environment fallback will be used.",
        "warning" if not swmm_python else "info",
    )

    openhydronet = detect_openhydronet_environment()
    ohn_status = str(openhydronet.get("status", "unknown"))
    _add(
        rows,
        "openhydronet_status",
        "passed" if ohn_status == "available" else "warning",
        ohn_status,
        "warning" if ohn_status != "available" else "info",
    )

    _add(rows, "external_gitignore", "passed" if _git_ignored("external/") else "failed", "external/")
    _add(
        rows,
        "streamlit_secrets_gitignore",
        "passed" if _git_ignored(".streamlit/secrets.toml") else "failed",
        ".streamlit/secrets.toml",
    )

    tracked = _tracked_files()
    tracked_forbidden = [
        path
        for path in tracked
        if path.lower().endswith(FORBIDDEN_SUFFIXES) or any(pattern in path.lower() for pattern in FORBIDDEN_PATTERNS)
    ]
    _add(
        rows,
        "tracked_secrets_or_weights",
        "failed" if tracked_forbidden else "passed",
        "; ".join(tracked_forbidden) if tracked_forbidden else "No tracked secrets, external repo files, or model weights detected.",
        "fatal" if tracked_forbidden else "info",
    )

    checks = pd.DataFrame(rows)
    output_dir = PROJECT_ROOT / "output" / "healthcheck"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_xlsx = output_dir / "healthcheck_summary.xlsx"
    report_md = output_dir / "healthcheck_report.md"
    with pd.ExcelWriter(summary_xlsx) as writer:
        checks.to_excel(writer, sheet_name="checks", index=False)
    failed = checks[checks["status"] == "failed"]
    warnings = checks[checks["status"] == "warning"]
    report_md.write_text(
        "\n".join(
            [
                f"# {__app_name__} Healthcheck",
                "",
                f"- Version: `{__version__}`",
                f"- Release date: `{__release_date__}`",
                f"- Python: `{sys.version.split()[0]}`",
                f"- Project root: `{PROJECT_ROOT}`",
                f"- Failed checks: `{len(failed)}`",
                f"- Warnings: `{len(warnings)}`",
                "",
                "## Checks",
                "",
                *[f"- `{row.check}`: `{row.status}` - {row.message}" for row in checks.itertuples(index=False)],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return HealthcheckOutputs(output_dir=output_dir, report_md=report_md, summary_xlsx=summary_xlsx, checks=checks)


def healthcheck_status(outputs: HealthcheckOutputs) -> str:
    if (outputs.checks["status"] == "failed").any():
        return "failed"
    if (outputs.checks["status"] == "warning").any():
        return "warning"
    return "passed"
