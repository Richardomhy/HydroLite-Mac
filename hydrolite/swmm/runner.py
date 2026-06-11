from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
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


def write_swmm_summary(path: Path, result: SwmmRunResult) -> None:
    data = asdict(result)
    df = pd.DataFrame([{column: data.get(column, pd.NA) for column in SWMM_SUMMARY_COLUMNS}])
    df.to_excel(path, index=False)


def read_swmm_summary(path: str | Path) -> pd.DataFrame:
    return pd.read_excel(path)


def _run_swmm_toolkit_subprocess(working_inp: Path, report_file: Path, output_file: Path) -> tuple[str, str]:
    code = """
from pathlib import Path
import sys
from swmm.toolkit import solver

inp, rpt, out = sys.argv[1:4]
if hasattr(solver, "swmm_run"):
    solver.swmm_run(inp, rpt, out)
elif hasattr(solver, "run"):
    solver.run(inp, rpt, out)
else:
    raise RuntimeError("swmm.toolkit.solver has no supported run function")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(working_inp), str(report_file), str(output_file)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if not detail:
            detail = f"SWMM subprocess exited with code {completed.returncode}"
        return "failed", detail
    return "success", ""


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

    if not inp_file.exists():
        result = SwmmRunResult(
            run_status="failed",
            inp_file=str(inp_file),
            working_inp=str(working_inp),
            report_file=str(report_file),
            output_file=str(output_file),
            error_message=f"SWMM inp_file does not exist: {inp_file}",
        )
        write_swmm_summary(summary_file, result)
        logger.warning(result.error_message)
        return result, summary_file

    shutil.copy2(inp_file, working_inp)
    logger.info("Copied SWMM inp_file to working file: %s -> %s", inp_file, working_inp)

    try:
        run_status, error_message = _run_swmm_toolkit_subprocess(
            working_inp, report_file, output_file
        )
    except subprocess.TimeoutExpired as exc:
        run_status = "failed"
        error_message = f"SWMM run timed out: {exc}"
    except Exception as exc:
        run_status = "failed"
        error_message = f"SWMM dependency unavailable or failed: {exc}"

    result = SwmmRunResult(
        run_status=run_status,
        inp_file=str(inp_file),
        working_inp=str(working_inp),
        report_file=str(report_file),
        output_file=str(output_file),
        error_message=error_message,
    )
    write_swmm_summary(summary_file, result)

    if run_status == "success":
        logger.info("SWMM run succeeded; wrote %s", summary_file)
    else:
        logger.warning("SWMM run %s: %s", run_status, error_message)
        logger.warning("HydroLite watershed outputs remain available.")
    return result, summary_file

