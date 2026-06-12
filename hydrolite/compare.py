from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from hydrolite.report import build_report


EXPECTED_FILES = {
    "result_flow.csv": "result_flow.csv",
    "summary.xlsx": "summary.xlsx",
    "water_balance.xlsx": "water_balance.xlsx",
    "swmm/swmm_summary.xlsx": "swmm/swmm_summary.xlsx",
    "swmm/swmm_kpis.xlsx": "swmm/swmm_kpis.xlsx",
    "swmm/coupling_summary.xlsx": "swmm/coupling_summary.xlsx",
}

OVERVIEW_COLUMNS = [
    "case_name",
    "output_folder",
    "has_hydrolite_result",
    "has_water_balance",
    "has_swmm",
    "has_coupling",
    "run_status",
    "notes",
]
HYDROLOGY_COLUMNS = [
    "case_name",
    "peak_flow",
    "peak_time",
    "total_runoff_volume_m3",
    "result_flow_csv",
]
WATER_BALANCE_COLUMNS = [
    "case_name",
    "max_subbasin_balance_error_percent",
    "outlet_balance_error_percent",
    "water_balance_file",
]
SWMM_COLUMNS = [
    "case_name",
    "swmm_status",
    "backend_used",
    "max_node_depth",
    "max_link_flow",
    "total_flooding_volume",
    "total_outflow_volume",
    "swmm_summary_file",
    "swmm_kpis_file",
]
COUPLING_COLUMNS = [
    "case_name",
    "coupling_enabled",
    "coupling_status",
    "target_node",
    "inflow_name",
    "timeseries_points",
    "max_flow",
    "total_inflow_volume_m3",
    "coupling_summary_file",
]
PERFORMANCE_COLUMNS = [
    "case_name",
    "NSE",
    "RMSE",
    "MAE",
    "PBIAS",
    "R2",
    "KGE",
    "n_pairs",
    "model_performance_file",
]
MISSING_COLUMNS = ["case_name", "expected_file", "status", "message"]


@dataclass(frozen=True)
class ComparisonOutputs:
    output_dir: Path
    xlsx: Path
    csv: Path
    peak_flow_png: Path
    volume_png: Path
    water_balance_png: Path
    swmm_kpi_png: Path
    report_md: Path


def discover_result_folders(output_root: str | Path) -> list[Path]:
    root = Path(output_root).expanduser().resolve()
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and path.name != "comparison"
        and not path.name.startswith(".")
        and any((path / expected).exists() for expected in EXPECTED_FILES)
    )


def _read_summary_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        df = pd.read_excel(path)
    except Exception:
        return {}
    if {"metric", "value"}.issubset(df.columns):
        return dict(zip(df["metric"].astype(str), df["value"]))
    if not df.empty:
        return df.iloc[0].to_dict()
    return {}


def _number(value: Any) -> float | None:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        return None
    return float(converted)


def _first_row(path: Path, sheet_name: str | int = 0) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return {}
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


def _hydrology_metrics(case_name: str, folder: Path) -> dict[str, Any]:
    result_path = folder / "result_flow.csv"
    summary_path = folder / "summary.xlsx"
    row: dict[str, Any] = {
        "case_name": case_name,
        "peak_flow": None,
        "peak_time": "",
        "total_runoff_volume_m3": None,
        "result_flow_csv": str(result_path) if result_path.exists() else "",
    }
    if not result_path.exists():
        return row

    try:
        df = pd.read_csv(result_path)
    except Exception:
        return row

    flow_col = "outflow_cms" if "outflow_cms" in df.columns else None
    if flow_col is None:
        numeric_cols = list(df.select_dtypes("number").columns)
        flow_col = numeric_cols[-1] if numeric_cols else None
    time_col = "time" if "time" in df.columns else ("datetime" if "datetime" in df.columns else df.columns[0])
    if flow_col is not None and not df.empty:
        flows = pd.to_numeric(df[flow_col], errors="coerce")
        if not flows.dropna().empty:
            peak_idx = flows.idxmax()
            row["peak_flow"] = float(flows.loc[peak_idx])
            row["peak_time"] = str(df.loc[peak_idx, time_col])

    summary = _read_summary_metrics(summary_path)
    volume = _number(summary.get("outflow_volume_m3"))
    if volume is None and flow_col is not None:
        flows = pd.to_numeric(df[flow_col], errors="coerce").fillna(0.0)
        volume = float(flows.sum() * 3600.0)
    row["total_runoff_volume_m3"] = volume
    return row


def _water_balance_metrics(case_name: str, folder: Path) -> dict[str, Any]:
    path = folder / "water_balance.xlsx"
    row: dict[str, Any] = {
        "case_name": case_name,
        "max_subbasin_balance_error_percent": None,
        "outlet_balance_error_percent": None,
        "water_balance_file": str(path) if path.exists() else "",
    }
    if not path.exists():
        return row
    try:
        subbasin = pd.read_excel(path, sheet_name="subbasin_balance")
        outlet = pd.read_excel(path, sheet_name="outlet_balance")
    except Exception:
        return row
    if "balance_error_percent" in subbasin.columns:
        values = pd.to_numeric(subbasin["balance_error_percent"], errors="coerce").abs()
        if not values.dropna().empty:
            row["max_subbasin_balance_error_percent"] = float(values.max())
    if "balance_error_percent" in outlet.columns and not outlet.empty:
        row["outlet_balance_error_percent"] = _number(outlet.loc[0, "balance_error_percent"])
    return row


def _swmm_metrics(case_name: str, folder: Path) -> dict[str, Any]:
    summary_path = folder / "swmm" / "swmm_summary.xlsx"
    kpis_path = folder / "swmm" / "swmm_kpis.xlsx"
    summary = _first_row(summary_path)
    kpis = _first_row(kpis_path)
    source = {**summary, **{key: value for key, value in kpis.items() if not pd.isna(value)}}
    return {
        "case_name": case_name,
        "swmm_status": source.get("run_status", ""),
        "backend_used": source.get("backend_used", ""),
        "max_node_depth": _number(source.get("max_node_depth")),
        "max_link_flow": _number(source.get("max_link_flow")),
        "total_flooding_volume": _number(source.get("total_flooding_volume")),
        "total_outflow_volume": _number(source.get("total_outflow_volume")),
        "swmm_summary_file": str(summary_path) if summary_path.exists() else "",
        "swmm_kpis_file": str(kpis_path) if kpis_path.exists() else "",
    }


def _coupling_metrics(case_name: str, folder: Path) -> dict[str, Any]:
    path = folder / "swmm" / "coupling_summary.xlsx"
    row = _first_row(path)
    return {
        "case_name": case_name,
        "coupling_enabled": row.get("coupling_enabled", ""),
        "coupling_status": row.get("coupling_status", ""),
        "target_node": row.get("target_node", ""),
        "inflow_name": row.get("inflow_name", ""),
        "timeseries_points": _number(row.get("timeseries_points")),
        "max_flow": _number(row.get("max_flow")),
        "total_inflow_volume_m3": _number(row.get("total_inflow_volume_m3")),
        "coupling_summary_file": str(path) if path.exists() else "",
    }


def _performance_metrics(case_name: str, folder: Path) -> dict[str, Any]:
    path = folder / "model_performance.xlsx"
    row = _first_row(path, sheet_name="metrics")
    return {
        "case_name": case_name,
        "NSE": _number(row.get("NSE")),
        "RMSE": _number(row.get("RMSE")),
        "MAE": _number(row.get("MAE")),
        "PBIAS": _number(row.get("PBIAS")),
        "R2": _number(row.get("R2")),
        "KGE": _number(row.get("KGE")),
        "n_pairs": _number(row.get("n_pairs")),
        "model_performance_file": str(path) if path.exists() else "",
    }


def _missing_rows(case_name: str, folder: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for expected in EXPECTED_FILES:
        path = folder / expected
        if not path.exists():
            rows.append(
                {
                    "case_name": case_name,
                    "expected_file": expected,
                    "status": "missing",
                    "message": f"{path} not found",
                }
            )
    return rows


def _plot_bar(df: pd.DataFrame, case_col: str, value_cols: list[str], path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    usable = [column for column in value_cols if column in df.columns and not df[column].dropna().empty]
    if df.empty or case_col not in df.columns or not usable:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_axis_off()
    else:
        plot_df = df[[case_col, *usable]].copy()
        for column in usable:
            plot_df[column] = pd.to_numeric(plot_df[column], errors="coerce")
        plot_df = plot_df.dropna(how="all", subset=usable)
        if plot_df.empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            ax.set_axis_off()
        else:
            plot_df.set_index(case_col)[usable].plot(kind="bar", ax=ax)
            ax.set_xlabel("case_name")
            ax.set_title(title)
            ax.grid(axis="y", alpha=0.3)
            ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _comparison_csv(
    overview: pd.DataFrame,
    hydrology: pd.DataFrame,
    water_balance: pd.DataFrame,
    swmm: pd.DataFrame,
    coupling: pd.DataFrame,
    performance: pd.DataFrame,
) -> pd.DataFrame:
    combined = overview.copy()
    for df in (hydrology, water_balance, swmm, coupling, performance):
        cols = [column for column in df.columns if column != "case_name"]
        combined = combined.merge(df[["case_name", *cols]], on="case_name", how="left")
    return combined


def run_compare(output_root: str | Path) -> ComparisonOutputs:
    root = Path(output_root).expanduser().resolve()
    comparison_dir = root / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    folders = discover_result_folders(root)
    overview_rows: list[dict[str, Any]] = []
    hydrology_rows: list[dict[str, Any]] = []
    water_rows: list[dict[str, Any]] = []
    swmm_rows: list[dict[str, Any]] = []
    coupling_rows: list[dict[str, Any]] = []
    performance_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []

    for folder in folders:
        case_name = folder.name
        hydrology = _hydrology_metrics(case_name, folder)
        water = _water_balance_metrics(case_name, folder)
        swmm = _swmm_metrics(case_name, folder)
        coupling = _coupling_metrics(case_name, folder)
        performance = _performance_metrics(case_name, folder)
        missing = _missing_rows(case_name, folder)

        has_hydrolite = bool(hydrology["result_flow_csv"])
        has_water = bool(water["water_balance_file"])
        has_swmm = bool(swmm["swmm_summary_file"])
        has_coupling = bool(coupling["coupling_summary_file"])
        run_status = "success" if has_hydrolite else "missing"
        if has_swmm and str(swmm["swmm_status"]).lower() == "failed":
            run_status = "failed"
        overview_rows.append(
            {
                "case_name": case_name,
                "output_folder": str(folder),
                "has_hydrolite_result": has_hydrolite,
                "has_water_balance": has_water,
                "has_swmm": has_swmm,
                "has_coupling": has_coupling,
                "run_status": run_status,
                "notes": "" if not missing else f"{len(missing)} expected outputs missing",
            }
        )
        hydrology_rows.append(hydrology)
        water_rows.append(water)
        swmm_rows.append(swmm)
        coupling_rows.append(coupling)
        performance_rows.append(performance)
        missing_rows.extend(missing)

    tables = {
        "overview": pd.DataFrame(overview_rows, columns=OVERVIEW_COLUMNS),
        "hydrology_metrics": pd.DataFrame(hydrology_rows, columns=HYDROLOGY_COLUMNS),
        "water_balance_metrics": pd.DataFrame(water_rows, columns=WATER_BALANCE_COLUMNS),
        "swmm_metrics": pd.DataFrame(swmm_rows, columns=SWMM_COLUMNS),
        "coupling_metrics": pd.DataFrame(coupling_rows, columns=COUPLING_COLUMNS),
        "performance_metrics": pd.DataFrame(performance_rows, columns=PERFORMANCE_COLUMNS),
        "missing_outputs": pd.DataFrame(missing_rows, columns=MISSING_COLUMNS),
    }

    outputs = ComparisonOutputs(
        output_dir=comparison_dir,
        xlsx=comparison_dir / "scenario_comparison.xlsx",
        csv=comparison_dir / "scenario_comparison.csv",
        peak_flow_png=comparison_dir / "peak_flow_comparison.png",
        volume_png=comparison_dir / "volume_comparison.png",
        water_balance_png=comparison_dir / "water_balance_comparison.png",
        swmm_kpi_png=comparison_dir / "swmm_kpi_comparison.png",
        report_md=comparison_dir / "hydrolite_report.md",
    )

    with pd.ExcelWriter(outputs.xlsx) as writer:
        for sheet_name, df in tables.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    _comparison_csv(
        tables["overview"],
        tables["hydrology_metrics"],
        tables["water_balance_metrics"],
        tables["swmm_metrics"],
        tables["coupling_metrics"],
        tables["performance_metrics"],
    ).to_csv(outputs.csv, index=False)

    _plot_bar(tables["hydrology_metrics"], "case_name", ["peak_flow"], outputs.peak_flow_png, "Peak Flow")
    _plot_bar(
        tables["hydrology_metrics"],
        "case_name",
        ["total_runoff_volume_m3"],
        outputs.volume_png,
        "Total Runoff Volume",
    )
    _plot_bar(
        tables["water_balance_metrics"],
        "case_name",
        ["max_subbasin_balance_error_percent", "outlet_balance_error_percent"],
        outputs.water_balance_png,
        "Water Balance Error",
    )
    _plot_bar(
        tables["swmm_metrics"],
        "case_name",
        ["max_node_depth", "max_link_flow", "total_flooding_volume", "total_outflow_volume"],
        outputs.swmm_kpi_png,
        "SWMM KPIs",
    )
    build_report(
        outputs.report_md,
        tables,
        {
            "scenario_comparison.xlsx": outputs.xlsx,
            "scenario_comparison.csv": outputs.csv,
            "peak_flow_comparison.png": outputs.peak_flow_png,
            "volume_comparison.png": outputs.volume_png,
            "water_balance_comparison.png": outputs.water_balance_png,
            "swmm_kpi_comparison.png": outputs.swmm_kpi_png,
            "hydrolite_report.md": outputs.report_md,
        },
    )
    return outputs
