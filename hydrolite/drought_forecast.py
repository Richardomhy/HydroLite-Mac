from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from hydrolite.continuous_hydrology import (
    DEFAULT_PARAMETERS,
    initialize_continuous_state,
    load_continuous_model_config,
    run_continuous_period,
    validate_continuous_water_balance,
)
from hydrolite.drought_classification import classify_drought_series
from hydrolite.drought_indices import calculate_composite_drought_index
from hydrolite.drought_scenarios import validate_drought_scenarios


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "drought_model" / "forecast"
LEAD_MONTHS = (1, 3, 6, 12)


def create_drought_forecast_config(project_dir: str | Path) -> Path:
    project = Path(project_dir).resolve()
    path = project / "drought_forecast_config.yaml"
    if path.exists():
        return path
    config = {
        "mode": "scenario_simulation",
        "analysis_date": None,
        "lead_months": list(LEAD_MONTHS),
        "maximum_members": 10,
        "continuous_model_config": "continuous_model_config.yaml",
        "scenario_config": {
            "source_csv": "daily_meteorology.csv",
            "precipitation_factors": [0.8, 0.6],
            "temperature_offsets_c": [1.0, 2.0],
            "pet_factors": [1.15],
        },
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def load_drought_forecast_config(path: str | Path) -> dict[str, Any]:
    file = Path(path).resolve()
    config = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    config["_config_path"] = str(file)
    return config


def validate_drought_forecast_config(config: dict[str, Any]) -> dict[str, Any]:
    errors = []
    mode = config.get("mode", "scenario_simulation")
    if mode not in {"scenario_simulation", "hindcast", "forecast"}:
        errors.append("mode must be scenario_simulation, hindcast, or forecast")
    leads = config.get("lead_months", LEAD_MONTHS)
    if not leads or any(int(value) not in LEAD_MONTHS for value in leads):
        errors.append(f"lead_months must be a subset of {LEAD_MONTHS}")
    maximum = int(config.get("maximum_members", 10))
    if not 1 <= maximum <= 100:
        errors.append("maximum_members must be between 1 and 100")
    if mode == "forecast" and not config.get("published_forecast_source"):
        errors.append("mode=forecast requires published_forecast_source")
    return {"status": "passed" if not errors else "failed", "errors": errors, "mode": mode}


def assess_drought_forecast_readiness(project_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    project = Path(project_dir)
    meteorology = project / "daily_meteorology.csv"
    continuous = project / config.get("continuous_model_config", "continuous_model_config.yaml")
    missing = [str(path) for path in (meteorology, continuous) if not path.exists()]
    real_observations = (project / "observed_streamflow.csv").exists() and not config.get("synthetic_demo", False)
    return {
        "status": "framework_ready_real_data_missing" if missing or not real_observations else "ready",
        "missing": missing,
        "synthetic_demo_available": meteorology.exists() and continuous.exists(),
        "real_data_readiness": "ready" if real_observations else "insufficient_data",
    }


def initialize_drought_forecast_state(project_dir: str | Path, analysis_date: Any) -> dict[str, Any]:
    project = Path(project_dir)
    config = load_continuous_model_config(project / "continuous_model_config.yaml")
    state_file = ROOT / "output" / "drought_model" / "continuous" / "daily_states.csv"
    state = initialize_continuous_state(config)
    if state_file.exists():
        states = pd.read_csv(state_file, parse_dates=["date"])
        cutoff = pd.Timestamp(analysis_date) if analysis_date else states["date"].max()
        preceding = states[states["date"] <= cutoff]
        if not preceding.empty:
            for subbasin_id, group in preceding.groupby("subbasin_id"):
                latest = group.sort_values("date").iloc[-1]
                if str(subbasin_id) in state["subbasins"]:
                    for field in state["subbasins"][str(subbasin_id)]:
                        if field in latest and pd.notna(latest[field]):
                            state["subbasins"][str(subbasin_id)][field] = float(latest[field])
    state["analysis_time"] = str(analysis_date)
    return state


def run_drought_forecast_member(
    state: dict[str, Any],
    forcing_member: pd.DataFrame,
    model: Callable[..., dict[str, Any]] | dict[str, Any],
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    config = deepcopy(model) if isinstance(model, dict) else {}
    member_id = str(forcing_member["member_id"].iloc[0]) if "member_id" in forcing_member and not forcing_member.empty else ""
    if member_id.startswith("pet_") and "potential_et_mm" in forcing_member:
        config["pet"] = {**config.get("pet", {}), "method": "user_supplied_pet"}
    parameters = {**DEFAULT_PARAMETERS, **config.get("parameters", {})}
    try:
        result = run_continuous_period(forcing_member, parameters, deepcopy(state), config)
        gate = validate_continuous_water_balance(result)
        status = "success" if gate["status"] == "passed" else "failed_water_balance"
        return {"status": status, "result": result, "water_balance": gate, "error_message": ""}
    except Exception as error:
        return {"status": "failed", "result": None, "water_balance": None, "error_message": str(error)}


def calculate_forecast_drought_indices(results: pd.DataFrame) -> pd.DataFrame:
    data = results.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["lead_month"] = ((data["date"].dt.year - data.groupby("member_id")["date"].transform("min").dt.year) * 12 + data["date"].dt.month - data.groupby("member_id")["date"].transform("min").dt.month + 1).clip(lower=1)
    monthly = data.groupby(["member_id", "lead_month"], as_index=False).agg(
        precipitation_mm=("precipitation_mm", "sum"),
        potential_et_mm=("potential_et_mm", "sum"),
        soil_moisture_mm=("soil_moisture_mm", "mean"),
        runoff_m3=("runoff_m3", "sum"),
        baseflow_mm=("baseflow_mm", "sum"),
        groundwater_storage_mm=("groundwater_storage_mm", "mean"),
        reservoir_storage_m3=("reservoir_storage_m3", "mean"),
    )
    for source, target in (
        ("precipitation_mm", "SPI"),
        ("soil_moisture_mm", "soil_moisture_percentile"),
        ("runoff_m3", "SSI"),
    ):
        monthly[target] = monthly.groupby("lead_month")[source].transform(
            lambda series: (series - series.mean()) / series.std(ddof=0) if series.std(ddof=0) > 0 else 0.0
        )
    water_balance = monthly["precipitation_mm"] - monthly["potential_et_mm"]
    monthly["SPEI"] = water_balance.groupby(monthly["lead_month"]).transform(
        lambda series: (series - series.mean()) / series.std(ddof=0) if series.std(ddof=0) > 0 else 0.0
    )
    monthly["composite_index"] = calculate_composite_drought_index(
        monthly[["SPI", "SPEI", "SSI"]],
        {"SPI": 0.35, "SPEI": 0.35, "SSI": 0.30},
    )
    monthly["drought_class"] = classify_drought_series(monthly["composite_index"])
    return monthly


def run_drought_forecast_ensemble(
    project_dir: str | Path,
    ensemble: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_drought_scenarios(ensemble)
    if validation["status"] != "passed":
        raise ValueError(f"Invalid scenario ensemble: {validation}")
    model_config = load_continuous_model_config(Path(project_dir) / config.get("continuous_model_config", "continuous_model_config.yaml"))
    max_members = int(config.get("maximum_members", 10))
    member_ids = list(ensemble["member_id"].drop_duplicates())[:max_members]
    analysis_date = config.get("analysis_date") or pd.to_datetime(ensemble["date"]).min() - pd.Timedelta(days=1)
    initial_state = initialize_drought_forecast_state(project_dir, analysis_date)
    rows, state_rows, failures = [], [], []
    for member_id in member_ids:
        forcing = ensemble[ensemble["member_id"] == member_id].copy()
        result = run_drought_forecast_member(initial_state, forcing, model_config)
        if result["status"] != "success":
            failures.append({"member_id": member_id, "status": result["status"], "error_message": result["error_message"]})
            continue
        model_result = result["result"]
        joined = model_result["fluxes"].merge(
            model_result["states"][["date", "subbasin_id", "upper_soil_storage_mm", "lower_soil_storage_mm", "groundwater_storage_mm", "reservoir_storage_m3"]],
            on=["date", "subbasin_id"],
        )
        routing = model_result["routing"][["date", "outflow_m3"]].rename(columns={"outflow_m3": "runoff_m3"})
        daily = joined.groupby("date", as_index=False).agg(
            precipitation_mm=("precipitation_mm", "mean"),
            potential_et_mm=("potential_et_mm", "mean"),
            baseflow_mm=("baseflow_mm", "mean"),
            upper_soil_storage_mm=("upper_soil_storage_mm", "mean"),
            lower_soil_storage_mm=("lower_soil_storage_mm", "mean"),
            groundwater_storage_mm=("groundwater_storage_mm", "mean"),
            reservoir_storage_m3=("reservoir_storage_m3", "mean"),
        ).merge(routing, on="date")
        daily["soil_moisture_mm"] = daily["upper_soil_storage_mm"] + daily["lower_soil_storage_mm"]
        daily["member_id"] = member_id
        daily["run_status"] = "success"
        rows.append(daily)
        for subbasin, values in model_result["final_state"]["subbasins"].items():
            state_rows.append({"member_id": member_id, "subbasin_id": subbasin, **values})
    daily_members = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    indices = calculate_forecast_drought_indices(daily_members) if not daily_members.empty else pd.DataFrame()
    mode = config.get("mode", "scenario_simulation")
    return {
        "status": "completed" if rows else "failed",
        "mode": mode,
        "probability_label": "probability" if mode == "forecast" else "scenario_member_fraction",
        "member_count": len(member_ids),
        "successful_members": len(rows),
        "failed_members": failures,
        "daily_members": daily_members,
        "state_members": pd.DataFrame(state_rows),
        "indices": indices,
        "analysis_date": str(pd.Timestamp(analysis_date)),
        "lead_months": [lead for lead in config.get("lead_months", LEAD_MONTHS) if not indices.empty and lead <= int(indices["lead_month"].max())],
        "uncertainty_sources": config.get("uncertainty_sources", ["climate_forcing", "initial_soil_state", "model_parameters", "PET_method", "reservoir_operation", "data_quality"]),
    }


def calculate_drought_onset_probability(results: pd.DataFrame, threshold: float = -1.0) -> pd.DataFrame:
    return results.assign(onset=results["composite_index"] <= threshold).groupby("lead_month", as_index=False)["onset"].mean().rename(columns={"onset": "onset_member_fraction"})


def calculate_drought_recovery_probability(results: pd.DataFrame, threshold: float = -0.5) -> pd.DataFrame:
    return results.assign(recovered=results["composite_index"] > threshold).groupby("lead_month", as_index=False)["recovered"].mean().rename(columns={"recovered": "recovery_member_fraction"})


def calculate_duration_distribution(results: pd.DataFrame, threshold: float = -1.0) -> pd.DataFrame:
    return results.assign(drought=results["composite_index"] <= threshold).groupby("member_id", as_index=False)["drought"].sum().rename(columns={"drought": "drought_duration_months"})


def calculate_severity_distribution(results: pd.DataFrame, threshold: float = -1.0) -> pd.DataFrame:
    frame = results.assign(deficit=(-results["composite_index"] - abs(threshold)).clip(lower=0))
    return frame.groupby("member_id", as_index=False)["deficit"].sum().rename(columns={"deficit": "cumulative_severity"})


def validate_drought_forecast_outputs(output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    required = [
        "forcing_members.csv", "state_members.csv", "drought_forecast_members.csv",
        "drought_index_quantiles.csv", "drought_class_members.xlsx", "drought_forecast_manifest.json",
    ]
    missing = [name for name in required if not (output / name).exists()]
    return {"status": "passed" if not missing else "failed", "missing": missing}


def write_drought_forecast_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    result["daily_members"].to_csv(output / "drought_forecast_members.csv", index=False)
    result["state_members"].to_csv(output / "state_members.csv", index=False)
    indices = result["indices"]
    quantiles = (
        indices.groupby("lead_month")["composite_index"].quantile([0.05, 0.25, 0.5, 0.75, 0.95]).unstack().reset_index().rename(columns={0.05:"p05",0.25:"p25",0.5:"p50",0.75:"p75",0.95:"p95"})
        if not indices.empty else pd.DataFrame(columns=["lead_month", "p05", "p25", "p50", "p75", "p95"])
    )
    quantiles.to_csv(output / "drought_index_quantiles.csv", index=False)
    with pd.ExcelWriter(output / "drought_class_members.xlsx") as writer:
        indices.to_excel(writer, sheet_name="members", index=False)
        (indices.groupby(["lead_month", "drought_class"]).size().rename("member_count").reset_index() if not indices.empty else pd.DataFrame()).to_excel(writer, sheet_name="fractions", index=False)
    onset = calculate_drought_onset_probability(indices) if not indices.empty else pd.DataFrame()
    recovery = calculate_drought_recovery_probability(indices) if not indices.empty else pd.DataFrame()
    duration = calculate_duration_distribution(indices) if not indices.empty else pd.DataFrame()
    severity = calculate_severity_distribution(indices) if not indices.empty else pd.DataFrame()
    onset.to_excel(output / "onset_distribution.xlsx", index=False)
    recovery.to_excel(output / "recovery_distribution.xlsx", index=False)
    duration.to_excel(output / "duration_distribution.xlsx", index=False)
    severity.to_excel(output / "severity_distribution.xlsx", index=False)
    if not quantiles.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.fill_between(quantiles["lead_month"], quantiles["p05"], quantiles["p95"], alpha=0.2)
        ax.plot(quantiles["lead_month"], quantiles["p50"], marker="o")
        ax.set_xlabel("lead month"); ax.set_ylabel("composite drought index")
        fig.tight_layout(); fig.savefig(output / "forecast_index_quantiles.png", dpi=130); plt.close(fig)
    if not indices.empty:
        fractions = indices.groupby(["lead_month", "drought_class"]).size().rename("count").reset_index()
        fractions["fraction"] = fractions["count"] / fractions.groupby("lead_month")["count"].transform("sum")
        pivot = fractions.pivot(index="lead_month", columns="drought_class", values="fraction").fillna(0)
        fig, ax = plt.subplots(figsize=(8, 4)); pivot.plot(kind="bar", stacked=True, ax=ax)
        fig.tight_layout(); fig.savefig(output / "drought_class_member_fraction.png", dpi=130); plt.close(fig)
    if not onset.empty:
        fig, ax = plt.subplots(figsize=(7, 4)); ax.plot(onset["lead_month"], onset["onset_member_fraction"], label="onset")
        ax.plot(recovery["lead_month"], recovery["recovery_member_fraction"], label="recovery"); ax.legend()
        fig.tight_layout(); fig.savefig(output / "onset_recovery_distribution.png", dpi=130); plt.close(fig)
    manifest = {
        "status": result["status"], "mode": result["mode"], "probability_label": result["probability_label"],
        "member_count": result["member_count"], "successful_members": result["successful_members"],
        "failed_members": result["failed_members"], "lead_months": result["lead_months"],
        "analysis_date": result["analysis_date"], "uncertainty_sources": result["uncertainty_sources"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / "drought_forecast_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    zh = output / "drought_forecast_report_zh.md"; en = output / "drought_forecast_report_en.md"
    zh.write_text(
        "# 干旱预测与情景集合\n\n"
        f"- 模式：`{result['mode']}`\n- 成员：`{result['successful_members']}/{result['member_count']}`\n"
        f"- 提前期：`{result['lead_months']}` 个月\n- 比例含义：`{result['probability_label']}`\n\n"
        "只有使用已发布预报产品时才称 forecast；Demo 与用户扰动均为情景模拟。软件诊断不等于法定干旱预警。\n",
        encoding="utf-8",
    )
    en.write_text(
        "# Drought Forecast and Scenario Ensemble\n\n"
        f"- mode: `{result['mode']}`\n- successful members: `{result['successful_members']}/{result['member_count']}`\n"
        f"- lead months: `{result['lead_months']}`\n- fraction label: `{result['probability_label']}`\n\n"
        "Forecast is used only for published forecast inputs. Demo and user perturbations are scenario simulations, not statutory drought warnings.\n",
        encoding="utf-8",
    )
    return {"members": output / "drought_forecast_members.csv", "quantiles": output / "drought_index_quantiles.csv", "manifest": output / "drought_forecast_manifest.json", "report_zh": zh, "report_en": en}


def export_drought_forecast_bundle(output_dir: str | Path) -> Path:
    output = Path(output_dir)
    bundle = output / "drought_forecast_bundle.zip"
    allowed = {".csv", ".xlsx", ".json", ".md", ".png"}
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path != bundle and path.suffix.lower() in allowed and not any(part in {"data_raw", "external"} for part in path.parts):
                archive.write(path, path.relative_to(output))
    return bundle
