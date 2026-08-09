from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
from typing import Any

import pandas as pd
import streamlit as st

from hydrolite.ui.state import PROJECT_ROOT


def read_text_if_exists(path: str | Path) -> str:
    text_path = Path(path)
    try:
        return text_path.read_text(encoding="utf-8") if text_path.exists() else ""
    except Exception as exc:
        return f"Unable to read {text_path}: {exc}"


def safe_read_csv(path: str | Path, nrows: int | None = None) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(csv_path, nrows=nrows)
    except Exception as exc:
        return pd.DataFrame({"error": [str(exc)], "file": [str(csv_path)]})


def safe_read_excel(path: str | Path, sheet_name: str | int = 0) -> pd.DataFrame:
    workbook = Path(path)
    if not workbook.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(workbook, sheet_name=sheet_name)
    except Exception as exc:
        return pd.DataFrame({"error": [str(exc)], "file": [str(workbook)]})


def read_result_flow(path: str | Path) -> pd.DataFrame:
    df = safe_read_csv(path)
    for column in ("time", "datetime"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
            break
    return df


def read_summary(path: str | Path) -> pd.DataFrame:
    return safe_read_excel(path)


def read_water_balance(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    return safe_read_excel(path, "subbasin_balance"), safe_read_excel(path, "outlet_balance")


def read_swmm_outputs(swmm_dir: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(swmm_dir)
    files = {
        "summary": root / "swmm_summary.xlsx",
        "kpis": root / "swmm_kpis.xlsx",
        "node_depth": root / "node_depth_timeseries.csv",
        "link_flow": root / "link_flow_timeseries.csv",
        "system": root / "system_timeseries.csv",
        "coupling": root / "coupling_summary.xlsx",
    }
    outputs: dict[str, pd.DataFrame] = {}
    for key, path in files.items():
        df = safe_read_excel(path) if path.suffix == ".xlsx" else safe_read_csv(path)
        if not df.empty:
            outputs[key] = df
    return outputs


def read_comparison_outputs(output_root: str | Path) -> dict[str, pd.DataFrame | Path]:
    root = Path(output_root) / "comparison"
    workbook = root / "scenario_comparison.xlsx"
    outputs: dict[str, pd.DataFrame | Path] = {}
    if workbook.exists():
        for sheet in (
            "overview",
            "hydrology_metrics",
            "water_balance_metrics",
            "swmm_metrics",
            "coupling_metrics",
            "performance_metrics",
        ):
            df = safe_read_excel(workbook, sheet)
            if not df.empty:
                outputs[sheet] = df
        outputs["scenario_comparison_xlsx"] = workbook
    for key, name in {
        "scenario_comparison_csv": "scenario_comparison.csv",
        "peak_flow_png": "peak_flow_comparison.png",
        "volume_png": "volume_comparison.png",
        "water_balance_png": "water_balance_comparison.png",
        "swmm_kpi_png": "swmm_kpi_comparison.png",
        "hydrolite_report_md": "hydrolite_report.md",
    }.items():
        path = root / name
        if path.exists():
            outputs[key] = path
    return outputs


def read_validation_outputs(output_root: str | Path) -> dict[str, pd.DataFrame | Path]:
    root = Path(output_root) / "validation"
    workbook = root / "validation_summary.xlsx"
    outputs: dict[str, pd.DataFrame | Path] = {}
    if workbook.exists():
        for sheet in ("overview", "checks", "errors", "warnings"):
            df = safe_read_excel(workbook, sheet)
            if not df.empty:
                outputs[sheet] = df
        outputs["validation_summary_xlsx"] = workbook
    for key, name in {
        "validation_summary_csv": "validation_summary.csv",
        "validation_report_md": "validation_report.md",
    }.items():
        path = root / name
        if path.exists():
            outputs[key] = path
    return outputs


def read_project_validation_outputs(project_dir: str | Path) -> dict[str, pd.DataFrame | Path]:
    reports = Path(project_dir) / "reports"
    workbook = reports / "project_validation.xlsx"
    outputs: dict[str, pd.DataFrame | Path] = {}
    if workbook.exists():
        for sheet in ("project_checks", "case_overview", "case_checks", "case_errors", "case_warnings"):
            df = safe_read_excel(workbook, sheet)
            if not df.empty:
                outputs[sheet] = df
        outputs["project_validation_xlsx"] = workbook
    report = reports / "project_validation_report.md"
    if report.exists():
        outputs["project_validation_report_md"] = report
    return outputs


def read_openhydronet_temperature_stats(path: str | Path = PROJECT_ROOT / "output" / "openhydronet" / "inputs" / "meteorological_forcing.csv") -> dict[str, object]:
    df = safe_read_csv(path)
    if df.empty or "temperature_mean_c" not in df.columns:
        return {"status": "missing", "non_null_ratio": 0.0, "min": None, "mean": None, "max": None}
    values = pd.to_numeric(df["temperature_mean_c"], errors="coerce")
    if values.notna().sum() == 0:
        return {"status": "all_na", "non_null_ratio": 0.0, "min": None, "mean": None, "max": None}
    return {
        "status": "available",
        "non_null_ratio": float(values.notna().mean()),
        "min": float(values.min()),
        "mean": float(values.mean()),
        "max": float(values.max()),
    }


def show_download(label: str, path: str | Path, mime: str) -> None:
    file_path = Path(path)
    if not file_path.exists():
        st.caption(f"{label}: unavailable")
        return
    st.download_button(label, file_path.read_bytes(), file_name=file_path.name, mime=mime)


def show_dataframe(title: str, df: pd.DataFrame, max_rows: int = 200) -> None:
    st.write(title)
    if df.empty:
        st.info("unavailable")
    else:
        st.dataframe(df.head(max_rows), use_container_width=True)


def show_markdown_file(title: str, path: str | Path) -> None:
    st.write(title)
    text = read_text_if_exists(path)
    if text:
        st.code(text, language="markdown")
    else:
        st.info("unavailable")


def show_json(data: Any) -> None:
    try:
        st.json(data)
    except Exception:
        st.code(json.dumps(data, indent=2, ensure_ascii=False), language="json")


def run_command(command: list[str], timeout: int = 180) -> tuple[bool, str]:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output.strip()


def run_python_module(args: list[str], timeout: int = 180) -> tuple[bool, str]:
    return run_command([sys.executable, "-m", *args], timeout=timeout)


def recent_files(root: str | Path, limit: int = 25) -> list[Path]:
    path = Path(root)
    if not path.exists():
        return []
    files = [item for item in path.rglob("*") if item.is_file()]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return files[:limit]


def output_dir_for_case(project_dir: str | Path, case_name: str) -> Path:
    return Path(project_dir) / "output" / case_name
