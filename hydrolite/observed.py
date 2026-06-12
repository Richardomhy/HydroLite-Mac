from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from hydrolite.metrics import calculate_all_metrics


def load_observed_streamflow(
    path: str | Path,
    time_column: str = "datetime",
    flow_column: str = "observed_streamflow_m3s",
    gauge_id_column: str = "gauge_id",
) -> pd.DataFrame:
    csv_path = Path(path).expanduser()
    if not csv_path.exists():
        raise FileNotFoundError(f"Observed streamflow CSV not found: {csv_path}")
    df = pd.read_csv(csv_path)
    missing = [column for column in [time_column, flow_column, gauge_id_column] if column not in df.columns]
    if missing:
        raise ValueError(f"Observed streamflow CSV missing columns: {missing}")
    out = df[[time_column, gauge_id_column, flow_column]].copy()
    out = out.rename(
        columns={
            time_column: "datetime",
            gauge_id_column: "gauge_id",
            flow_column: "observed_streamflow_m3s",
        }
    )
    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    out["observed_streamflow_m3s"] = pd.to_numeric(out["observed_streamflow_m3s"], errors="coerce")
    return out


def validate_observed_streamflow(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def add(name: str, status: str, message: str, severity: str = "info") -> None:
        rows.append({"check_name": name, "status": status, "message": message, "severity": severity})

    required = ["datetime", "gauge_id", "observed_streamflow_m3s"]
    for column in required:
        add(f"field:{column}", "passed" if column in df.columns else "failed", f"{column} {'exists' if column in df.columns else 'missing'}", "fatal" if column not in df.columns else "info")
    if not set(required).issubset(df.columns):
        return pd.DataFrame(rows), pd.DataFrame(warnings, columns=["warning_name", "message", "severity"])
    add(
        "datetime_parseable",
        "failed" if df["datetime"].isna().any() else "passed",
        "datetime contains unparseable values" if df["datetime"].isna().any() else "datetime parseable",
        "fatal" if df["datetime"].isna().any() else "info",
    )
    flow = pd.to_numeric(df["observed_streamflow_m3s"], errors="coerce")
    bad_flow = flow.isna().any() or (flow < 0).any()
    add(
        "observed_streamflow_non_negative",
        "failed" if bad_flow else "passed",
        "observed_streamflow_m3s must be numeric and non-negative" if bad_flow else "observed streamflow is numeric and non-negative",
        "fatal" if bad_flow else "info",
    )
    bad_gauge = df["gauge_id"].isna().any() or (df["gauge_id"].astype(str).str.strip() == "").any()
    add(
        "gauge_id_present",
        "failed" if bad_gauge else "passed",
        "gauge_id cannot be empty" if bad_gauge else "gauge_id populated",
        "fatal" if bad_gauge else "info",
    )
    if df.empty:
        add("row_count", "failed", "observed streamflow has no rows", "fatal")
    if len(df["gauge_id"].dropna().astype(str).unique()) > 1:
        warnings.append(
            {
                "warning_name": "multiple_gauge_ids",
                "message": "Observed streamflow contains multiple gauge_id values.",
                "severity": "warning",
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(warnings, columns=["warning_name", "message", "severity"])


def align_observed_and_simulated(
    observed_df: pd.DataFrame,
    simulated_df: pd.DataFrame,
    observed_time_col: str = "datetime",
    simulated_time_col: str = "time",
    observed_flow_col: str = "observed_streamflow_m3s",
    simulated_flow_col: str = "outflow_cms",
) -> pd.DataFrame:
    observed = observed_df[[observed_time_col, "gauge_id", observed_flow_col]].copy()
    simulated = simulated_df[[simulated_time_col, simulated_flow_col]].copy()
    observed["datetime"] = pd.to_datetime(observed[observed_time_col], errors="coerce")
    simulated["datetime"] = pd.to_datetime(simulated[simulated_time_col], errors="coerce")
    observed["observed_streamflow_m3s"] = pd.to_numeric(observed[observed_flow_col], errors="coerce")
    simulated["simulated_streamflow_m3s"] = pd.to_numeric(simulated[simulated_flow_col], errors="coerce")
    return observed[["datetime", "gauge_id", "observed_streamflow_m3s"]].merge(
        simulated[["datetime", "simulated_streamflow_m3s"]], on="datetime", how="inner"
    )


def write_observed_quality_report(path: str | Path, sheets: dict[str, pd.DataFrame]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path) as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    return output_path


def plot_observed_vs_simulated(aligned: pd.DataFrame, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if aligned.empty:
        ax.text(0.5, 0.5, "No aligned observed/simulated data", ha="center", va="center")
        ax.set_axis_off()
    else:
        plot_df = aligned.copy()
        plot_df["datetime"] = pd.to_datetime(plot_df["datetime"], errors="coerce")
        plot_df = plot_df.dropna(subset=["datetime"]).set_index("datetime")
        ax.plot(plot_df.index, plot_df["observed_streamflow_m3s"], label="Observed", marker="o", linewidth=1.2)
        ax.plot(plot_df.index, plot_df["simulated_streamflow_m3s"], label="Simulated", marker="s", linewidth=1.2)
        ax.set_ylabel("Streamflow (m3/s)")
        ax.grid(alpha=0.3)
        ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def build_model_performance(
    case_name: str,
    observed_file: str | Path,
    simulated_file: str | Path,
    observed_df: pd.DataFrame,
    simulated_df: pd.DataFrame,
    simulated_flow_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    aligned = align_observed_and_simulated(observed_df, simulated_df, simulated_flow_col=simulated_flow_col)
    checks, observed_warnings = validate_observed_streamflow(observed_df)
    metrics = calculate_all_metrics(aligned.get("observed_streamflow_m3s", []), aligned.get("simulated_streamflow_m3s", []))
    metric_warnings = [
        {"warning_name": "metric_warning", "message": message, "severity": "warning"}
        for message in metrics.pop("warnings", [])
    ]
    gauge_id = "" if aligned.empty else str(aligned["gauge_id"].dropna().iloc[0])
    metrics_row = {
        "case_name": case_name,
        "gauge_id": gauge_id,
        **metrics,
        "observed_file": str(observed_file),
        "simulated_file": str(simulated_file),
        "synthetic_demo_only": True,
    }
    warnings = pd.concat([observed_warnings, pd.DataFrame(metric_warnings)], ignore_index=True)
    return pd.DataFrame([metrics_row]), aligned, checks, warnings
