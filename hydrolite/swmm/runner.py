from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import logging
import os
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
    "external_solver_available",
    "external_solver_python",
    "external_solver_status",
    "external_solver_summary_json",
    "solver_env_diagnosis_file",
    "node_depth_timeseries_csv",
    "link_flow_timeseries_csv",
    "system_timeseries_csv",
    "swmm_kpis_xlsx",
    "result_extraction_errors",
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
    external_solver_available: bool = False
    external_solver_python: str = ""
    external_solver_status: str = ""
    external_solver_summary_json: str = ""
    solver_env_diagnosis_file: str = ""
    node_depth_timeseries_csv: str = ""
    link_flow_timeseries_csv: str = ""
    system_timeseries_csv: str = ""
    swmm_kpis_xlsx: str = ""
    result_extraction_errors: str = ""


def write_swmm_summary(path: Path, result: SwmmRunResult) -> None:
    data = asdict(result)
    df = pd.DataFrame([{column: data.get(column, pd.NA) for column in SWMM_SUMMARY_COLUMNS}])
    df.to_excel(path, index=False)


def read_swmm_summary(path: str | Path) -> pd.DataFrame:
    return pd.read_excel(path)


def write_swmm_kpis(path: Path, kpis: dict[str, object]) -> None:
    columns = [
        "run_status",
        "backend_used",
        "max_node_depth",
        "max_link_flow",
        "total_flooding_volume",
        "total_outflow_volume",
        "node_count",
        "link_count",
        "report_file",
        "output_file",
    ]
    pd.DataFrame([{column: kpis.get(column, pd.NA) for column in columns}]).to_excel(
        path, index=False
    )


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


def _solver_env_diagnosis_file(case_output_dir: Path) -> Path:
    return case_output_dir.parent / "swmm_solver_env_diagnosis.txt"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _conda_env_python() -> Path | None:
    try:
        completed = subprocess.run(
            ["conda", "info", "--base"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    base = completed.stdout.strip()
    if not base:
        return None
    return Path(base) / "envs" / "hydrolite-swmm-x64" / "bin" / "python"


def find_external_solver_python() -> Path | None:
    env_value = os.environ.get("HYDROLITE_SWMM_PYTHON")
    if env_value:
        path = Path(env_value).expanduser()
        if path.exists():
            return path.resolve()
    conda_python = _conda_env_python()
    if conda_python and conda_python.exists():
        return conda_python.resolve()
    return None


def _attempt_external_solver(
    working_inp: Path,
    report_file: Path,
    output_file: Path,
    summary_json: Path,
) -> tuple[dict[str, object], dict[str, object] | None]:
    external_python = find_external_solver_python()
    if external_python is None:
        return (
            {
                "backend_name": "external_solver",
                "backend_available": False,
                "backend_status": "failed",
                "return_code": "",
                "error_message": "No isolated SWMM Python found via HYDROLITE_SWMM_PYTHON or conda env hydrolite-swmm-x64.",
                "external_solver_python": "",
                "external_solver_summary_json": str(summary_json),
            },
            None,
        )

    script = _project_root() / "scripts" / "swmm_env" / "run_swmm_solver.py"
    completed = subprocess.run(
        [
            str(external_python),
            str(script),
            "--inp",
            str(working_inp),
            "--rpt",
            str(report_file),
            "--out",
            str(output_file),
            "--summary",
            str(summary_json),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    payload = None
    if summary_json.exists():
        try:
            payload = json.loads(summary_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
    message = (completed.stderr or completed.stdout or "").strip()
    if payload and payload.get("error_message"):
        message = str(payload["error_message"])
    if completed.returncode != 0 and not message:
        message = f"external_solver exited with code {completed.returncode}"

    return (
        {
            "backend_name": "external_solver",
            "backend_available": True,
            "backend_status": "success" if completed.returncode == 0 else "failed",
            "return_code": completed.returncode,
            "error_message": "" if completed.returncode == 0 else message,
            "external_solver_python": str(external_python),
            "external_solver_summary_json": str(summary_json),
        },
        payload,
    )


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
    kpis_file = swmm_dir / "swmm_kpis.xlsx"
    diagnosis_file = _diagnosis_file(case_output_dir)
    solver_env_diagnosis_file = _solver_env_diagnosis_file(case_output_dir)
    external_summary_json = swmm_dir / "external_solver_summary.json"
    node_depth_csv = swmm_dir / "node_depth_timeseries.csv"
    link_flow_csv = swmm_dir / "link_flow_timeseries.csv"
    system_csv = swmm_dir / "system_timeseries.csv"

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
            solver_env_diagnosis_file=str(solver_env_diagnosis_file),
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
    external_solver_python = ""
    external_solver_status = ""
    external_payload: dict[str, object] | None = None
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
        external_attempt, external_payload = _attempt_external_solver(
            working_inp, swmm_dir / "model.rpt", swmm_dir / "model.out", external_summary_json
        )
        attempts.append(external_attempt)
        external_solver_python = str(external_attempt.get("external_solver_python", ""))
        external_solver_status = str(external_attempt["backend_status"])
        logger.info(
            "SWMM backend attempt: backend_name=%s, backend_available=%s, "
            "backend_status=%s, return_code=%s",
            external_attempt["backend_name"],
            external_attempt["backend_available"],
            external_attempt["backend_status"],
            external_attempt["return_code"],
        )
        if external_attempt["error_message"]:
            logger.warning(
                "SWMM backend %s error: %s",
                external_attempt["backend_name"],
                external_attempt["error_message"],
            )
        if external_attempt["backend_status"] == "success":
            backend_used = "external_solver"
            if external_payload and external_payload.get("backend_used"):
                backend_used = f"external_solver:{external_payload['backend_used']}"
            run_status = "success"

    if run_status != "success":
        error_message = "; ".join(
            f"{item['backend_name']}: {item['error_message'] or 'failed'}"
            for item in attempts
        )

    external_kpis = external_payload.get("kpis", {}) if external_payload else {}
    extraction_errors = (
        external_payload.get("result_extraction_errors", []) if external_payload else []
    )
    final_report_file = (
        str(external_kpis.get("report_file"))
        if isinstance(external_kpis, dict) and external_kpis.get("report_file")
        else str(report_file)
    )
    final_output_file = (
        str(external_kpis.get("output_file"))
        if isinstance(external_kpis, dict) and external_kpis.get("output_file")
        else str(output_file)
    )
    kpis = {
        "run_status": run_status,
        "backend_used": backend_used,
        "max_node_depth": external_kpis.get("max_node_depth", pd.NA)
        if isinstance(external_kpis, dict)
        else pd.NA,
        "max_link_flow": external_kpis.get("max_link_flow", pd.NA)
        if isinstance(external_kpis, dict)
        else pd.NA,
        "total_flooding_volume": external_kpis.get("total_flooding_volume", pd.NA)
        if isinstance(external_kpis, dict)
        else pd.NA,
        "total_outflow_volume": external_kpis.get("total_outflow_volume", pd.NA)
        if isinstance(external_kpis, dict)
        else pd.NA,
        "node_count": external_kpis.get("node_count", pd.NA)
        if isinstance(external_kpis, dict)
        else pd.NA,
        "link_count": external_kpis.get("link_count", pd.NA)
        if isinstance(external_kpis, dict)
        else pd.NA,
        "report_file": final_report_file,
        "output_file": final_output_file,
    }
    write_swmm_kpis(kpis_file, kpis)

    result = SwmmRunResult(
        run_status=run_status,
        inp_file=str(inp_file),
        working_inp=str(working_inp),
        report_file=final_report_file,
        output_file=final_output_file,
        total_flooding_volume=kpis["total_flooding_volume"],
        total_outflow_volume=kpis["total_outflow_volume"],
        max_node_depth=kpis["max_node_depth"],
        max_link_flow=kpis["max_link_flow"],
        error_message=error_message,
        backend_used=backend_used,
        backend_attempts=json.dumps(attempts, ensure_ascii=False),
        diagnosis_file=str(diagnosis_file),
        external_solver_available=bool(external_solver_python),
        external_solver_python=external_solver_python,
        external_solver_status=external_solver_status,
        external_solver_summary_json=str(external_summary_json),
        solver_env_diagnosis_file=str(solver_env_diagnosis_file),
        node_depth_timeseries_csv=str(node_depth_csv),
        link_flow_timeseries_csv=str(link_flow_csv),
        system_timeseries_csv=str(system_csv),
        swmm_kpis_xlsx=str(kpis_file),
        result_extraction_errors=json.dumps(extraction_errors, ensure_ascii=False),
    )
    write_swmm_summary(summary_file, result)
    if extraction_errors:
        logger.warning("SWMM result extraction issues: %s", extraction_errors)

    if run_status == "success":
        logger.info("SWMM run succeeded; wrote %s", summary_file)
    else:
        logger.warning("SWMM run %s: %s", run_status, error_message)
        logger.warning("HydroLite watershed outputs remain available.")
    return result, summary_file
