from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import logging
import shutil
import subprocess
import sys

import pandas as pd


SWMM_SUMMARY_COLUMNS = [
    "run_status",
    "inp_file",
    "working_inp",
    "report_file",
    "output_file",
    "total_flooding_volume",
    "total_outflow_volume",
    "max_node_depth",
    "max_link_flow",
    "error_message",
    "backend_used",
    "backend_attempts",
    "diagnosis_file",
]


@dataclass(frozen=True)
class SwmmRunResult:
    run_status: str
    inp_file: str
    working_inp: str
    report_file: str
    output_file: str
    total_flooding_volume: object = pd.NA
    total_outflow_volume: object = pd.NA
    max_node_depth: object = pd.NA
    max_link_flow: object = pd.NA
    error_message: str = ""
    backend_used: str = ""
    backend_attempts: str = ""
    diagnosis_file: str = ""


def write_swmm_summary(path: Path, result: SwmmRunResult) -> None:
    data = asdict(result)
    df = pd.DataFrame([{column: data.get(column, pd.NA) for column in SWMM_SUMMARY_COLUMNS}])
    df.to_excel(path, index=False)


def read_swmm_summary(path: str | Path) -> pd.DataFrame:
    return pd.read_excel(path)


def _attempt(
    backend_name: str,
    code: str,
    working_inp: Path,
    report_file: Path,
    output_file: Path,
) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-c", code, str(working_inp), str(report_file), str(output_file)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    error_message = (completed.stderr or completed.stdout or "").strip()
    if completed.returncode != 0 and not error_message:
        error_message = f"{backend_name} subprocess exited with code {completed.returncode}"
    return {
        "backend_name": backend_name,
        "backend_available": completed.returncode != 127,
        "backend_status": "success" if completed.returncode == 0 else "failed",
        "return_code": completed.returncode,
        "error_message": error_message,
    }


def _import_backend(backend_name: str) -> dict[str, object]:
    snippets = {
        "pyswmm": "from pyswmm import Simulation; print('ok')",
        "swmm-toolkit": "from swmm.toolkit import solver; print('ok')",
        "swmm_api": "from swmm_api import swmm5_run; print('ok')",
    }
    completed = subprocess.run(
        [sys.executable, "-c", snippets[backend_name]],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    message = (completed.stderr or completed.stdout or "").strip()
    if completed.returncode != 0 and not message:
        message = f"{backend_name} import exited with code {completed.returncode}"
    return {
        "return_code": completed.returncode,
        "error_message": "" if completed.returncode == 0 else message,
    }


def _attempt_backend(
    backend_name: str,
    working_inp: Path,
    report_file: Path,
    output_file: Path,
) -> dict[str, object]:
    snippets = {
        "pyswmm": """
import sys
from pyswmm import Simulation

inp, rpt, out = sys.argv[1:4]
with Simulation(inp) as sim:
    for _ in sim:
        pass
""",
        "swmm-toolkit": """
import sys
from swmm.toolkit import solver

inp, rpt, out = sys.argv[1:4]
if hasattr(solver, "swmm_run"):
    solver.swmm_run(inp, rpt, out)
elif hasattr(solver, "run"):
    solver.run(inp, rpt, out)
else:
    raise RuntimeError("swmm.toolkit.solver has no supported run function")
""",
        "swmm_api": """
import sys
from swmm_api import swmm5_run

inp, rpt, out = sys.argv[1:4]
swmm5_run(inp, rpt, out)
""",
    }
    try:
        import_result = _import_backend(backend_name)
    except subprocess.TimeoutExpired as exc:
        return {
            "backend_name": backend_name,
            "backend_available": False,
            "backend_status": "failed",
            "return_code": "",
            "error_message": f"{backend_name} import timed out: {exc}",
        }
    if import_result["return_code"] != 0:
        return {
            "backend_name": backend_name,
            "backend_available": False,
            "backend_status": "failed",
            "return_code": import_result["return_code"],
            "error_message": import_result["error_message"],
        }
    try:
        return _attempt(backend_name, snippets[backend_name], working_inp, report_file, output_file)
    except subprocess.TimeoutExpired as exc:
        return {
            "backend_name": backend_name,
            "backend_available": True,
            "backend_status": "failed",
            "return_code": "",
            "error_message": f"{backend_name} timed out: {exc}",
        }
    except Exception as exc:
        return {
            "backend_name": backend_name,
            "backend_available": False,
            "backend_status": "failed",
            "return_code": "",
            "error_message": f"{backend_name} unavailable or failed: {exc}",
        }


def _diagnosis_file(case_output_dir: Path) -> Path:
    return case_output_dir.parent / "swmm_backend_diagnosis.txt"


def run_swmm(
    *,
    inp_file: Path,
    case_output_dir: Path,
    logger: logging.Logger,
) -> tuple[SwmmRunResult, Path]:
    swmm_dir = case_output_dir / "swmm"
    swmm_dir.mkdir(parents=True, exist_ok=True)
    working_inp = swmm_dir / "working.inp"
    report_file = swmm_dir / "working.rpt"
    output_file = swmm_dir / "working.out"
    summary_file = swmm_dir / "swmm_summary.xlsx"
    diagnosis_file = _diagnosis_file(case_output_dir)

    if not inp_file.exists():
        attempts: list[dict[str, object]] = []
        result = SwmmRunResult(
            run_status="failed",
            inp_file=str(inp_file),
            working_inp=str(working_inp),
            report_file=str(report_file),
            output_file=str(output_file),
            error_message=f"SWMM inp_file does not exist: {inp_file}",
            backend_used="",
            backend_attempts=json.dumps(attempts, ensure_ascii=False),
            diagnosis_file=str(diagnosis_file),
        )
        write_swmm_summary(summary_file, result)
        logger.warning(result.error_message)
        return result, summary_file

    shutil.copy2(inp_file, working_inp)
    logger.info("Copied SWMM inp_file to working file: %s -> %s", inp_file, working_inp)

    attempts = []
    backend_used = ""
    run_status = "failed"
    error_message = ""
    for backend_name in ("pyswmm", "swmm-toolkit", "swmm_api"):
        attempt = _attempt_backend(backend_name, working_inp, report_file, output_file)
        attempts.append(attempt)
        logger.info(
            "SWMM backend attempt: backend_name=%s, backend_available=%s, "
            "backend_status=%s, return_code=%s",
            attempt["backend_name"],
            attempt["backend_available"],
            attempt["backend_status"],
            attempt["return_code"],
        )
        if attempt["error_message"]:
            logger.warning(
                "SWMM backend %s error: %s",
                attempt["backend_name"],
                attempt["error_message"],
            )
        if attempt["backend_status"] == "success":
            backend_used = str(attempt["backend_name"])
            run_status = "success"
            break

    if run_status != "success":
        error_message = "; ".join(
            f"{item['backend_name']}: {item['error_message'] or 'failed'}"
            for item in attempts
        )

    result = SwmmRunResult(
        run_status=run_status,
        inp_file=str(inp_file),
        working_inp=str(working_inp),
        report_file=str(report_file),
        output_file=str(output_file),
        error_message=error_message,
        backend_used=backend_used,
        backend_attempts=json.dumps(attempts, ensure_ascii=False),
        diagnosis_file=str(diagnosis_file),
    )
    write_swmm_summary(summary_file, result)

    if run_status == "success":
        logger.info("SWMM run succeeded; wrote %s", summary_file)
    else:
        logger.warning("SWMM run %s: %s", run_status, error_message)
        logger.warning("HydroLite watershed outputs remain available.")
    return result, summary_file
