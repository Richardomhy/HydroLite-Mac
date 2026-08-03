from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd
import yaml

from hydrolite.continuous_hydrology import DEFAULT_PARAMETERS, initialize_continuous_state, load_continuous_model_config, run_continuous_period
from hydrolite.metrics import kge, nse, pbias


DEFAULT_MULTI_OBJECTIVE_WEIGHTS = {"NSE": .15, "log_NSE": .10, "KGE": .15, "absolute_PBIAS": .15, "monthly_volume_error_percent": .10, "peak_flow_error_percent": .10, "low_flow_RMSE": .10, "flow_duration_curve_error": .10, "water_balance_penalty": .05}


def normalize_objective_weights(weights: dict[str, float] | None, available: set[str]) -> dict[str, float]:
    chosen={name:float(value) for name,value in (weights or DEFAULT_MULTI_OBJECTIVE_WEIGHTS).items() if name in available}
    total=sum(chosen.values()); return {name:value/total for name,value in chosen.items()} if total else {}


def calculate_multiobjective_score(metrics: dict[str, float], weights: dict[str, float] | None = None) -> float:
    available={name for name,value in metrics.items() if value is not None and np.isfinite(value)};normalized=normalize_objective_weights(weights,available);score=0.0
    for name,weight in normalized.items():
        value=float(metrics[name]); score += weight*(value if name in {"NSE","log_NSE","KGE"} else -abs(value))
    return score


def build_staged_calibration_plan(parameters: dict[str, float]) -> dict[str, Any]:
    return {"stages":[{"name":"water_balance","parameters":["et_coefficient","upper_soil_capacity_mm","lower_soil_capacity_mm","deep_loss_coefficient"],"max_candidates":30},{"name":"low_flow","parameters":["baseflow_coefficient","percolation_coefficient","groundwater_recharge_coefficient"],"max_candidates":30},{"name":"high_flow","parameters":["infiltration_coefficient","interflow_coefficient"],"max_candidates":30},{"name":"joint_refinement","parameters":list(build_continuous_parameter_bounds(parameters)),"max_candidates":10}],"total_candidate_cap":100}


def run_water_balance_stage(*args, **kwargs): return {"status":"planned_lightweight_stage"}
def run_low_flow_stage(*args, **kwargs): return {"status":"planned_lightweight_stage"}
def run_high_flow_stage(*args, **kwargs): return {"status":"planned_lightweight_stage"}
def run_joint_refinement_stage(*args, **kwargs): return {"status":"planned_lightweight_stage"}
def validate_staged_calibration(result: dict[str, Any]) -> dict[str, Any]: return {"status":"passed" if result.get("candidate_count",0)<=100 else "failed"}


def split_continuous_periods_chronologically(data: pd.DataFrame, config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    ordered = data.sort_values("date").reset_index(drop=True)
    calibration_fraction = float(config.get("calibration_fraction", 0.6))
    validation_fraction = float(config.get("validation_fraction", 0.2))
    first = int(len(ordered) * calibration_fraction)
    second = first + int(len(ordered) * validation_fraction)
    return {
        "calibration": ordered.iloc[:first].copy(),
        "validation": ordered.iloc[first:second].copy(),
        "test": ordered.iloc[second:].copy(),
    }


def build_continuous_calibration_periods(data: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for name, frame in split_continuous_periods_chronologically(data, config).items():
        rows.append({"period": name, "start": frame["date"].min(), "end": frame["date"].max(), "records": len(frame)})
    return pd.DataFrame(rows)


def collect_continuous_parameters(project_dir: str | Path) -> dict[str, float]:
    config = load_continuous_model_config(Path(project_dir) / "continuous_model_config.yaml")
    return {**DEFAULT_PARAMETERS, **config.get("parameters", {})}


def build_continuous_parameter_bounds(parameters: dict[str, float]) -> dict[str, tuple[float, float]]:
    scalable = (
        "interception_capacity_mm", "infiltration_coefficient", "upper_soil_capacity_mm",
        "lower_soil_capacity_mm", "percolation_coefficient", "interflow_coefficient",
        "baseflow_coefficient", "et_coefficient",
    )
    bounds = {}
    for key in scalable:
        value = float(parameters[key])
        lower, upper = value * 0.7, value * 1.3
        if "coefficient" in key:
            lower, upper = max(0.0, lower), min(1.0, upper)
        bounds[key] = (lower, upper)
    return bounds


def evaluate_continuous_model(simulated: pd.Series | np.ndarray, observed: pd.Series | np.ndarray) -> dict[str, float]:
    sim, obs = np.asarray(simulated, dtype=float), np.asarray(observed, dtype=float)
    mask = np.isfinite(sim) & np.isfinite(obs)
    sim, obs = sim[mask], obs[mask]
    if len(sim) < 2:
        return {key: np.nan for key in ("NSE", "log_NSE", "KGE", "RMSE", "MAE", "PBIAS", "flow_duration_curve_error")}
    fdc_error = np.mean(np.abs(np.sort(sim) - np.sort(obs))) / max(np.mean(np.abs(obs)), 1e-9) * 100
    return {
        "NSE": float(nse(obs, sim)),
        "log_NSE": float(nse(np.log1p(obs), np.log1p(sim))),
        "KGE": float(kge(obs, sim)),
        "RMSE": float(np.sqrt(np.mean((sim - obs) ** 2))),
        "MAE": float(np.mean(np.abs(sim - obs))),
        "PBIAS": float(pbias(obs, sim)),
        "flow_duration_curve_error": float(fdc_error),
    }


def evaluate_low_flow_performance(simulated, observed) -> dict[str, float]:
    sim, obs = np.asarray(simulated, dtype=float), np.asarray(observed, dtype=float)
    threshold = np.nanquantile(obs, 0.3)
    mask = obs <= threshold
    return {"low_flow_RMSE": float(np.sqrt(np.nanmean((sim[mask] - obs[mask]) ** 2))), "low_flow_bias": float(np.nanmean(sim[mask] - obs[mask]))}


def evaluate_high_flow_performance(simulated, observed) -> dict[str, float]:
    sim, obs = np.asarray(simulated, dtype=float), np.asarray(observed, dtype=float)
    threshold = np.nanquantile(obs, 0.9)
    mask = obs >= threshold
    return {"high_flow_RMSE": float(np.sqrt(np.nanmean((sim[mask] - obs[mask]) ** 2))), "peak_flow_error_percent": float((np.nanmax(sim) - np.nanmax(obs)) / max(np.nanmax(obs), 1e-9) * 100)}


def calculate_water_balance_penalty(result: dict[str, Any]) -> float:
    return abs(float(result["water_balance"]["cumulative_water_balance_residual_mm"])) * 1000.0


def detect_continuous_overfitting(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty or not {"calibration_NSE", "validation_NSE"} <= set(results):
        return {"status": "unavailable"}
    gap = float((results["calibration_NSE"] - results["validation_NSE"]).max())
    return {"status": "warning" if gap > 0.25 else "passed", "maximum_NSE_gap": gap}


def select_robust_continuous_parameters(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {"status": "missing"}
    score = results.get("validation_KGE", pd.Series(-np.inf, index=results.index)).fillna(-np.inf) - results.get("water_balance_penalty", 0)
    row = results.loc[score.idxmax()].to_dict()
    parameters = row.get("parameters", {})
    if isinstance(parameters, str):
        parameters = json.loads(parameters)
    return {"status": "selected", "candidate_id": row.get("candidate_id"), "parameters": parameters, "metrics": {key: value for key, value in row.items() if key != "parameters"}}


def run_continuous_parameter_search(project_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    project = Path(project_dir)
    model_config = load_continuous_model_config(project / "continuous_model_config.yaml")
    base = Path(model_config["_config_path"]).parent
    forcing = pd.read_csv(base / model_config["input"]["daily_meteorology_csv"])
    observed_path = project / "observed_streamflow.csv"
    max_candidates = min(max(int(config.get("max_candidates", 30)), 1), 60)
    if not observed_path.exists():
        return {"status": "framework_ready_real_data_missing", "candidate_count": 0, "successful_candidates": 0, "results": pd.DataFrame(), "message": "observed_streamflow.csv is required for real calibration"}
    observed = pd.read_csv(observed_path)
    if len(observed) < 365:
        return {"status": "insufficient_data", "candidate_count": 0, "successful_candidates": 0, "results": pd.DataFrame()}
    forcing["date"] = pd.to_datetime(forcing["date"])
    observed["date"] = pd.to_datetime(observed["date"])
    observed = observed.rename(columns={"streamflow_cms": "observed_flow_cms"})
    periods_table = build_continuous_calibration_periods(observed, config).to_dict("records")
    base_parameters = {**DEFAULT_PARAMETERS, **model_config.get("parameters", {})}
    bounds = build_continuous_parameter_bounds(base_parameters)
    rng = np.random.default_rng(42)
    rows = []
    for candidate in range(max_candidates):
        parameters = dict(base_parameters)
        for name, (lower, upper) in bounds.items():
            parameters[name] = float(rng.uniform(lower, upper))
        try:
            result = run_continuous_period(forcing, parameters, initialize_continuous_state(model_config), model_config)
            daily = result["routing"].groupby("date", as_index=False)["outflow_m3"].sum()
            daily["flow_cms"] = daily["outflow_m3"] / 86400.0
            aligned = daily.merge(observed[["date", "observed_flow_cms"]], on="date")
            periods = split_continuous_periods_chronologically(aligned, config)
            row = {"candidate_id": candidate + 1, "parameters": json.dumps(parameters), "water_balance_penalty": calculate_water_balance_penalty(result)}
            for name, frame in periods.items():
                metrics = evaluate_continuous_model(frame["flow_cms"], frame["observed_flow_cms"])
                metrics.update(evaluate_low_flow_performance(frame["flow_cms"], frame["observed_flow_cms"]))
                metrics.update(evaluate_high_flow_performance(frame["flow_cms"], frame["observed_flow_cms"]))
                dated = frame.assign(period=pd.to_datetime(frame["date"]).dt.to_period("M"))
                monthly = dated.groupby("period")[["flow_cms", "observed_flow_cms"]].sum()
                metrics["monthly_volume_error_percent"] = float(
                    np.mean(np.abs(monthly["flow_cms"] - monthly["observed_flow_cms"]))
                    / max(np.mean(np.abs(monthly["observed_flow_cms"])), 1e-9) * 100
                )
                metrics["annual_balance_error_percent"] = float(
                    (frame["flow_cms"].sum() - frame["observed_flow_cms"].sum())
                    / max(abs(frame["observed_flow_cms"].sum()), 1e-9) * 100
                )
                row.update({f"{name}_{key}": value for key, value in metrics.items()})
            rows.append(row)
        except Exception as error:
            rows.append({"candidate_id": candidate + 1, "error": str(error), "parameters": json.dumps(parameters)})
    results = pd.DataFrame(rows)
    successful = int(results.get("calibration_NSE", pd.Series(dtype=float)).notna().sum())
    return {
        "status": "completed" if successful else "failed",
        "mode": "synthetic_demo" if bool(observed.get("synthetic_demo", pd.Series(False)).all()) else "real_observations",
        "candidate_count": max_candidates,
        "successful_candidates": successful,
        "periods": periods_table,
        "results": results,
        "selection": select_robust_continuous_parameters(results.dropna(subset=["calibration_NSE"])) if successful else {"status": "missing"},
    }


def write_continuous_calibration_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results = result.get("results", pd.DataFrame())
    results.to_excel(output / "candidates.xlsx", index=False)
    pd.DataFrame(result.get("periods", [])).to_excel(output / "calibration_periods.xlsx", index=False)
    selection = result.get("selection", {})
    (output / "robust_parameters.yaml").write_text(yaml.safe_dump(selection.get("parameters", {}), sort_keys=False), encoding="utf-8")
    for language, name in (("zh", "continuous_calibration_report_zh.md"), ("en", "continuous_calibration_report_en.md")):
        text = "# 连续模型率定\n\n" if language == "zh" else "# Continuous Model Calibration\n\n"
        text += f"- status: `{result.get('status')}`\n- candidates: `{result.get('candidate_count', 0)}`\n- successful: `{result.get('successful_candidates', 0)}`\n\n"
        text += "No real calibration is claimed when observations are missing; periods are chronological and never shuffled.\n"
        (output / name).write_text(text, encoding="utf-8")
    return {"candidates": output / "candidates.xlsx", "parameters": output / "robust_parameters.yaml", "report_zh": output / "continuous_calibration_report_zh.md", "report_en": output / "continuous_calibration_report_en.md"}
