from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

import pandas as pd

from hydrolite.compare import run_compare
from hydrolite.config import load_case
from hydrolite.runner import run_case
from hydrolite.validate import validate_target


def discover_case_files(cases_dir: str | Path) -> list[Path]:
    root = Path(cases_dir).expanduser().resolve()
    files = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml"))
    return sorted(files)


def _project_root(cases_dir: Path) -> Path:
    return cases_dir.parent if cases_dir.name == "cases" else Path.cwd().resolve()


def _successful_case_row(
    case_file: Path,
    case_name: str,
    start_time: datetime,
    end_time: datetime,
    runtime_seconds: float,
    output_folder: Path,
    validation_status: str = "passed",
    validation_message: str = "",
) -> dict[str, object]:
    result = pd.read_csv(output_folder / "result_flow.csv")
    peak_idx = int(result["outflow_cms"].idxmax())
    water_balance = pd.read_excel(output_folder / "water_balance.xlsx", sheet_name="outlet_balance")

    return {
        "case_file": str(case_file),
        "case_name": case_name,
        "status": "success",
        "start_time": start_time.isoformat(timespec="seconds"),
        "end_time": end_time.isoformat(timespec="seconds"),
        "runtime_seconds": runtime_seconds,
        "output_folder": str(output_folder),
        "peak_flow": float(result.loc[peak_idx, "outflow_cms"]),
        "peak_time": str(result.loc[peak_idx, "time"]),
        "total_runoff_volume_m3": float(water_balance.loc[0, "total_inflow_volume_m3"]),
        "water_balance_error_percent": float(water_balance.loc[0, "balance_error_percent"]),
        "error_message": "",
        "validation_status": validation_status,
        "validation_message": validation_message,
    }


def _failed_case_row(
    case_file: Path,
    case_name: str,
    start_time: datetime,
    end_time: datetime,
    runtime_seconds: float,
    output_folder: Path | None,
    error: Exception,
    validation_status: str = "",
    validation_message: str = "",
) -> dict[str, object]:
    return {
        "case_file": str(case_file),
        "case_name": case_name,
        "status": "failed",
        "start_time": start_time.isoformat(timespec="seconds"),
        "end_time": end_time.isoformat(timespec="seconds"),
        "runtime_seconds": runtime_seconds,
        "output_folder": "" if output_folder is None else str(output_folder),
        "peak_flow": "",
        "peak_time": "",
        "total_runoff_volume_m3": "",
        "water_balance_error_percent": "",
        "error_message": str(error),
        "validation_status": validation_status,
        "validation_message": validation_message,
    }


def _failed_validation_case_row(
    case_file: Path,
    case_name: str,
    start_time: datetime,
    end_time: datetime,
    runtime_seconds: float,
    output_folder: Path | None,
    validation_message: str,
) -> dict[str, object]:
    return {
        "case_file": str(case_file),
        "case_name": case_name,
        "status": "failed_validation",
        "start_time": start_time.isoformat(timespec="seconds"),
        "end_time": end_time.isoformat(timespec="seconds"),
        "runtime_seconds": runtime_seconds,
        "output_folder": "" if output_folder is None else str(output_folder),
        "peak_flow": "",
        "peak_time": "",
        "total_runoff_volume_m3": "",
        "water_balance_error_percent": "",
        "error_message": validation_message,
        "validation_status": "failed",
        "validation_message": validation_message,
    }


def run_batch(cases_dir: str | Path) -> tuple[Path, list[dict[str, object]], list[str]]:
    cases_path = Path(cases_dir).expanduser().resolve()
    output_root = _project_root(cases_path) / "output"
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "batch_summary.xlsx"

    rows: list[dict[str, object]] = []
    failed_cases: list[str] = []
    validation = validate_target(cases_path)
    validation_by_file = {
        str(Path(row["case_file"]).resolve()): row
        for _, row in validation.overview.iterrows()
    }

    for case_file in discover_case_files(cases_path):
        started = time.perf_counter()
        start_time = datetime.now()
        output_folder: Path | None = None
        case_name = case_file.stem
        validation_row = validation_by_file.get(str(case_file.resolve()), {})
        validation_status = str(validation_row.get("validation_status", "passed"))
        validation_message = str(validation_row.get("message", ""))
        try:
            if validation_status == "failed":
                case_name = str(validation_row.get("case_name", case_name))
                output_folder = output_root / case_name if case_name else None
                end_time = datetime.now()
                runtime_seconds = time.perf_counter() - started
                failed_cases.append(str(case_file))
                rows.append(
                    _failed_validation_case_row(
                        case_file,
                        case_name,
                        start_time,
                        end_time,
                        runtime_seconds,
                        output_folder,
                        validation_message,
                    )
                )
                continue
            config = load_case(case_file)
            case_name = config.name
            output_folder = output_root / case_name
            run_case(case_file, output_dir=output_folder, skip_validate=True)
            end_time = datetime.now()
            runtime_seconds = time.perf_counter() - started
            rows.append(
                _successful_case_row(
                    case_file,
                    case_name,
                    start_time,
                    end_time,
                    runtime_seconds,
                    output_folder,
                    validation_status=validation_status,
                    validation_message=validation_message,
                )
            )
        except Exception as exc:
            end_time = datetime.now()
            runtime_seconds = time.perf_counter() - started
            failed_cases.append(str(case_file))
            rows.append(
                _failed_case_row(
                    case_file,
                    case_name,
                    start_time,
                    end_time,
                    runtime_seconds,
                    output_folder,
                    exc,
                    validation_status=validation_status,
                    validation_message=validation_message,
                )
            )

    pd.DataFrame(rows).to_excel(summary_path, index=False)
    try:
        run_compare(output_root)
    except Exception as exc:
        print(f"WARNING scenario comparison failed after batch run: {exc}")
    return summary_path, rows, failed_cases
