from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hydrolite.hindcast_metrics import calculate_hindcast_metrics


DEFAULT_LEAD_TIMES = [1, 3, 6, 12]


def generate_forecast_cycles(event: pd.DataFrame, lead_times: list[int] | None = None, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    frame = event.copy()
    times = pd.to_datetime(frame["timestamp"], errors="coerce")
    dt = times.diff().dt.total_seconds().median() / 3600 if len(times) > 1 else 1.0
    cycles = []
    for lead in lead_times or DEFAULT_LEAD_TIMES:
        steps = max(1, round(lead / dt))
        for index in range(0, len(frame) - steps):
            cycles.append({
                "analysis_index": index, "verification_index": index + steps, "analysis_time": times.iloc[index],
                "forecast_start": times.iloc[index], "forecast_end": times.iloc[index + steps],
                "lead_time_hr": lead, "steps": steps,
            })
    return cycles


def run_open_loop_forecast_cycle(event: pd.DataFrame, cycle: dict[str, Any]) -> dict[str, Any]:
    row = event.iloc[int(cycle["verification_index"])]
    return {**cycle, "method": "open_loop", "forecast_flow_cms": float(row["open_loop_flow_cms"]), "observed_flow_cms": float(row["observed_flow_cms"])}


def run_assimilated_forecast_cycle(event: pd.DataFrame, cycle: dict[str, Any], method: str = "nudging", decay: float = .8) -> dict[str, Any]:
    analysis = event.iloc[int(cycle["analysis_index"])]
    verification = event.iloc[int(cycle["verification_index"])]
    correction_source = "nudging_analysis_flow_cms" if method == "nudging" else "enkf_analysis_flow_cms"
    correction = float(analysis[correction_source]) - float(analysis["open_loop_flow_cms"])
    steps = int(cycle["steps"])
    forecast = max(0.0, float(verification["open_loop_flow_cms"]) + correction * decay**steps)
    return {**cycle, "method": method, "forecast_flow_cms": forecast, "observed_flow_cms": float(verification["observed_flow_cms"]), "result_type": "forecast_from_analysis"}


def calculate_lead_time_metrics(results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (lead, method), group in results.groupby(["lead_time_hr", "method"]):
        metrics = calculate_hindcast_metrics(group["observed_flow_cms"], group["forecast_flow_cms"])["summary"]
        rows.append({"lead_time_hr": lead, "method": method, **metrics})
    return pd.DataFrame(rows)


def aggregate_lead_time_metrics(results: pd.DataFrame) -> pd.DataFrame:
    metrics = calculate_lead_time_metrics(results)
    open_loop = metrics[metrics["method"] == "open_loop"].set_index("lead_time_hr")
    rows = []
    for _, row in metrics.iterrows():
        baseline = open_loop.loc[row["lead_time_hr"]] if row["lead_time_hr"] in open_loop.index else None
        improvement = np.nan
        if baseline is not None and row["method"] != "open_loop" and pd.notna(baseline["RMSE"]) and baseline["RMSE"] != 0:
            improvement = 1 - float(row["RMSE"]) / float(baseline["RMSE"])
        rows.append({**row.to_dict(), "skill_improvement": improvement, "uncertainty_coverage": np.nan, "spread": np.nan, "uncertainty_status": "exploratory"})
    return pd.DataFrame(rows)


def plot_skill_vs_lead_time(results: pd.DataFrame, path: str | Path) -> Path | None:
    if results.empty:
        return None
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    for method, group in results.groupby("method"):
        ax.plot(group["lead_time_hr"], group["RMSE"], marker="o", label=method)
    ax.set(xlabel="Lead time (h)", ylabel="RMSE (m3/s)", title="Forecast Skill vs Lead Time")
    ax.grid(alpha=.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)
    return output


def write_lead_time_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for language, title in (("zh", "多提前期验证报告"), ("en", "Lead-time Validation Report")):
        path = output / f"lead_time_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Forecast cycles: `{result.get('cycle_count', 0)}`\n"
            "- Lead times: `1h, 3h, 6h, 12h` when event length permits.\n"
            "- Assimilated forecasts use only observations available at analysis time; future observations are not leaked.\n"
            "- Uncertainty coverage is exploratory until enough independent real events are available.\n",
            encoding="utf-8",
        )
        paths[language] = path
    return paths


def run_lead_time_validation(assimilation_dir: str | Path, output_dir: str | Path, lead_times: list[int] | None = None) -> dict[str, Any]:
    source = Path(assimilation_dir) / "analysis_timeseries.csv"
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        result = {"status": "missing_data", "cycle_count": 0, "metrics": pd.DataFrame()}
        write_lead_time_report(output, result)
        return result
    frame = pd.read_csv(source)
    rows = []
    for _, event in frame.groupby("event_id"):
        event = event.sort_values("timestamp").reset_index(drop=True)
        for cycle in generate_forecast_cycles(event, lead_times):
            rows.append(run_open_loop_forecast_cycle(event, cycle))
            rows.append(run_assimilated_forecast_cycle(event, cycle, "nudging"))
            rows.append(run_assimilated_forecast_cycle(event, cycle, "enkf"))
            analysis = event.iloc[int(cycle["analysis_index"])]
            verification = event.iloc[int(cycle["verification_index"])]
            rows.append({**cycle, "method": "persistence", "forecast_flow_cms": float(analysis["observed_flow_cms"]), "observed_flow_cms": float(verification["observed_flow_cms"])})
    cycles = pd.DataFrame(rows)
    metrics = aggregate_lead_time_metrics(cycles) if not cycles.empty else pd.DataFrame()
    with pd.ExcelWriter(output / "lead_time_metrics.xlsx") as writer:
        cycles.to_excel(writer, sheet_name="cycles", index=False)
        metrics.to_excel(writer, sheet_name="metrics", index=False)
    metrics.to_excel(output / "lead_time_summary.xlsx", index=False)
    plot_skill_vs_lead_time(metrics, output / "skill_vs_lead_time.png")
    result = {"status": "passed" if len(metrics) else "missing_data", "cycle_count": len(cycles), "metrics": metrics}
    write_lead_time_report(output, result)
    return result
