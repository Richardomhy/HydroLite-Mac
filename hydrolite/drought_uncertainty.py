from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


QUANTILES = (0.05, 0.25, 0.50, 0.75, 0.95)


def collect_drought_members(results) -> pd.DataFrame:
    if isinstance(results, pd.DataFrame): return results.copy()
    if isinstance(results, dict) and "indices" in results: return results["indices"].copy()
    return pd.concat(list(results), ignore_index=True)


def calculate_index_quantiles(results: pd.DataFrame) -> pd.DataFrame:
    values = results.groupby("lead_month")["composite_index"].quantile(QUANTILES).unstack()
    values.columns = ["p05", "p25", "p50", "p75", "p95"]
    return values.reset_index()


def calculate_drought_class_fraction(results: pd.DataFrame) -> pd.DataFrame:
    counts = results.groupby(["lead_month", "drought_class"]).size().rename("count").reset_index()
    counts["scenario_member_fraction"] = counts["count"] / counts.groupby("lead_month")["count"].transform("sum")
    return counts


def calculate_onset_time_distribution(results: pd.DataFrame, threshold: float = -1.0) -> pd.DataFrame:
    rows = []
    for member_id, frame in results.sort_values("lead_month").groupby("member_id"):
        active = frame[frame["composite_index"] <= threshold]
        rows.append({"member_id": member_id, "onset_lead_month": int(active["lead_month"].min()) if not active.empty else None})
    return pd.DataFrame(rows)


def calculate_recovery_time_distribution(results: pd.DataFrame, threshold: float = -0.5) -> pd.DataFrame:
    rows = []
    for member_id, frame in results.sort_values("lead_month").groupby("member_id"):
        drought = frame["composite_index"] <= -1
        recovered = frame.loc[drought.cummax() & (frame["composite_index"] > threshold)]
        rows.append({"member_id": member_id, "recovery_lead_month": int(recovered["lead_month"].min()) if not recovered.empty else None})
    return pd.DataFrame(rows)


def calculate_duration_distribution(results: pd.DataFrame) -> pd.DataFrame:
    return results.assign(active=results["composite_index"] <= -1).groupby("member_id", as_index=False)["active"].sum().rename(columns={"active":"duration_months"})


def calculate_severity_distribution(results: pd.DataFrame) -> pd.DataFrame:
    return results.assign(deficit=(-results["composite_index"] - 1).clip(lower=0)).groupby("member_id", as_index=False)["deficit"].sum().rename(columns={"deficit":"severity"})


def calculate_storage_deficit_distribution(results: pd.DataFrame) -> pd.DataFrame:
    if "reservoir_storage_m3" not in results: return pd.DataFrame(columns=["member_id", "storage_deficit"])
    maximum = results["reservoir_storage_m3"].max()
    return results.assign(storage_deficit=maximum-results["reservoir_storage_m3"]).groupby("member_id", as_index=False)["storage_deficit"].max()


def classify_drought_uncertainty_sources(config: dict[str, Any]) -> list[dict[str, str]]:
    default = ["climate_forcing", "initial_soil_state", "groundwater_state", "model_parameters", "model_structure", "PET_method", "reservoir_operation", "data_quality", "unresolved"]
    active = set(config.get("uncertainty_sources", default))
    return [{"source": source, "status": "represented" if source in active else "not_represented"} for source in default]


def write_drought_uncertainty_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    report = output / "drought_uncertainty_report.md"
    report.write_text(
        "# Drought forecast uncertainty\n\n"
        f"- fraction label: `{result.get('probability_label', 'scenario_member_fraction')}`\n"
        f"- sources: `{result.get('uncertainty_sources', [])}`\n\n"
        "Scenario member fractions are not probabilities unless the forcing is a formally calibrated probabilistic ensemble.\n",
        encoding="utf-8",
    )
    return report
