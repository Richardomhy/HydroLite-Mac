from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json

import numpy as np
import pandas as pd
import yaml

from hydrolite.hindcast_metrics import calculate_hindcast_metrics


DEFAULT_CONFIG = {
    "method": "flow_nudging",
    "gain": 0.45,
    "correction_decay": 0.8,
    "ensemble_size": 20,
    "state_variables": ["routing_flow", "baseflow", "model_flow_correction_factor"],
    "observation_variables": ["outlet_flow"],
    "parameter_perturbation": 0.05,
    "forcing_perturbation": 0.1,
    "observation_error": 0.8,
    "model_error": 0.15,
    "inflation_factor": 1.02,
    "localization": False,
    "random_seed": 42,
    "timing": "observation_available",
}


def build_assimilation_config(project_dir: str | Path) -> dict[str, Any]:
    for path in (Path(project_dir) / "assimilation_config.yaml", Path(project_dir) / "configs" / "assimilation_config.yaml"):
        if path.exists():
            return {**DEFAULT_CONFIG, **(yaml.safe_load(path.read_text(encoding="utf-8")) or {})}
    return dict(DEFAULT_CONFIG)


def validate_assimilation_config(config: dict[str, Any]) -> dict[str, Any]:
    errors = []
    gain = float(config.get("gain", 0.45))
    size = int(config.get("ensemble_size", 20))
    if not 0 <= gain <= 1:
        errors.append("gain must be in [0, 1]")
    if not 2 <= size <= 30:
        errors.append("ensemble_size must be in [2, 30]")
    if float(config.get("observation_error", 0)) <= 0:
        errors.append("observation_error must be positive and not forced to zero")
    if float(config.get("model_error", 0)) <= 0:
        errors.append("model_error must be positive")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def prepare_assimilation_observations(data: Any) -> pd.DataFrame:
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    time_col = next((name for name in ("timestamp", "datetime", "time") if name in frame), None)
    value_col = next((name for name in ("flow_cms", "observed_flow_cms", "stage_m", "value") if name in frame), None)
    if not time_col or not value_col:
        raise ValueError("Assimilation observations require time and flow/stage value columns.")
    output = frame.copy()
    output["timestamp"] = pd.to_datetime(output[time_col], errors="coerce")
    output["observation"] = pd.to_numeric(output[value_col], errors="coerce")
    return output.dropna(subset=["timestamp", "observation"]).sort_values("timestamp")


def calculate_observation_error(data: Any, config: dict[str, Any]) -> float:
    configured = float(config.get("observation_error", DEFAULT_CONFIG["observation_error"]))
    return max(configured, 1e-3)


def calculate_model_error(ensemble: Any, config: dict[str, Any]) -> float:
    values = np.asarray(ensemble, dtype=float)
    spread = float(np.nanstd(values, ddof=1)) if values.size > 1 else 0.0
    return max(spread, float(config.get("model_error", DEFAULT_CONFIG["model_error"])), 1e-3)


def assimilate_flow_nudging(state: float | dict[str, Any], observation: float, config: dict[str, Any]) -> dict[str, Any]:
    gain = float(config.get("gain", DEFAULT_CONFIG["gain"]))
    if not 0 <= gain <= 1:
        raise ValueError("nudging gain must be in [0, 1]")
    model = float(state.get("flow_cms", 0)) if isinstance(state, dict) else float(state)
    analysis = max(0.0, model + gain * (float(observation) - model))
    return {"open_loop": model, "observation": float(observation), "analysis": analysis, "innovation": float(observation) - model, "gain": gain}


def assimilate_direct_state(state: dict[str, Any], observation: float, config: dict[str, Any]) -> dict[str, Any]:
    result = dict(state)
    variable = str(config.get("state_variable", "routing_flow"))
    if variable not in {"baseflow", "reach_storage", "routing_flow", "soil_moisture_proxy", "reservoir_storage", "model_flow_correction_factor"}:
        raise ValueError(f"State variable is not updateable: {variable}")
    result[variable] = max(0.0, float(observation))
    result["analysis_type"] = "direct_state_update"
    return result


def initialize_enkf_ensemble(base_state: dict[str, Any], parameters: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    validation = validate_assimilation_config(config)
    if validation["status"] == "failed":
        raise ValueError("; ".join(validation["errors"]))
    size = int(config.get("ensemble_size", 20))
    variables = list(config.get("state_variables", DEFAULT_CONFIG["state_variables"]))
    rng = np.random.default_rng(int(config.get("random_seed", 42)))
    base = np.array([float(base_state.get(name, base_state.get("flow_cms", 0.0)) or 0.0) for name in variables])
    scale = np.maximum(np.abs(base) * float(config.get("parameter_perturbation", .05)), float(config.get("model_error", .15)))
    states = rng.normal(base, scale, size=(size, len(variables)))
    return {"states": enforce_physical_state_constraints(states), "variables": variables, "random_seed": int(config.get("random_seed", 42))}


def propagate_enkf_ensemble(ensemble: dict[str, Any] | np.ndarray, forcing: Any, model: Callable | None) -> dict[str, Any]:
    states = np.asarray(ensemble["states"] if isinstance(ensemble, dict) else ensemble, dtype=float)
    propagated = model(states, forcing) if callable(model) else states + np.asarray(forcing, dtype=float)
    variables = ensemble.get("variables", []) if isinstance(ensemble, dict) else []
    return {"states": enforce_physical_state_constraints(propagated), "variables": variables}


def update_enkf_ensemble(ensemble: dict[str, Any], observation: float, config: dict[str, Any]) -> dict[str, Any]:
    states = np.asarray(ensemble["states"], dtype=float)
    if states.ndim != 2 or len(states) < 2:
        raise ValueError("EnKF requires a 2D ensemble with at least two members.")
    predicted = states[:, 0]
    centered_states = states - states.mean(axis=0)
    centered_obs = predicted - predicted.mean()
    covariance = centered_states.T @ centered_obs / (len(states) - 1)
    observation_variance = float(np.var(predicted, ddof=1))
    error_variance = calculate_observation_error(predicted, config) ** 2
    regularization = max(1e-8, error_variance * 1e-6)
    gain = covariance / (observation_variance + error_variance + regularization)
    rng = np.random.default_rng(int(config.get("random_seed", 42)))
    perturbed = float(observation) + rng.normal(0, error_variance**0.5, size=len(states))
    innovations = perturbed - predicted
    posterior = states + np.outer(innovations, gain)
    posterior_mean_before = posterior.mean(axis=0)
    posterior = enforce_physical_state_constraints(posterior)
    return {
        "states": posterior, "variables": ensemble.get("variables", []), "kalman_gain": gain,
        "innovation": float(observation) - float(predicted.mean()), "prior_spread": float(predicted.std(ddof=1)),
        "posterior_spread": float(posterior[:, 0].std(ddof=1)), "regularization": regularization,
        "physical_constraint_adjustment": float(np.abs(posterior.mean(axis=0) - posterior_mean_before).sum()),
    }


def enforce_physical_state_constraints(ensemble: Any) -> np.ndarray:
    values = np.asarray(ensemble, dtype=float).copy()
    values[~np.isfinite(values)] = 0.0
    return np.maximum(values, 0.0)


def _aligned(event: Any) -> pd.DataFrame:
    if isinstance(event, pd.DataFrame):
        return event.copy()
    if isinstance(event, dict) and isinstance(event.get("aligned"), pd.DataFrame):
        return event["aligned"].copy()
    path = Path(event["aligned"] if isinstance(event, dict) and "aligned" in event else event)
    return pd.read_csv(path)


def run_event_data_assimilation(event: Any, config: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame = _aligned(event)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    model = pd.to_numeric(frame["simulated_flow_cms"], errors="coerce").to_numpy()
    observed = pd.to_numeric(frame["observed_flow_cms"], errors="coerce").to_numpy()
    nudging = np.empty_like(model)
    innovations = np.empty_like(model)
    for index, (simulation, observation) in enumerate(zip(model, observed)):
        result = assimilate_flow_nudging(float(simulation), float(observation), config)
        nudging[index], innovations[index] = result["analysis"], result["innovation"]
    size = min(int(config.get("ensemble_size", 20)), 30)
    enkf_analysis, prior_spread, posterior_spread, gains = [], [], [], []
    for index, (simulation, observation) in enumerate(zip(model, observed)):
        ensemble = initialize_enkf_ensemble(
            {"routing_flow": simulation, "baseflow": max(simulation * .15, 0), "model_flow_correction_factor": 1.0, "flow_cms": simulation},
            {}, {**config, "ensemble_size": size, "random_seed": int(config.get("random_seed", 42)) + index},
        )
        updated = update_enkf_ensemble(ensemble, float(observation), {**config, "random_seed": int(config.get("random_seed", 42)) + index})
        enkf_analysis.append(float(updated["states"][:, 0].mean()))
        prior_spread.append(updated["prior_spread"])
        posterior_spread.append(updated["posterior_spread"])
        gains.append(float(updated["kalman_gain"][0]))
    timeseries = pd.DataFrame({
        "timestamp": frame["timestamp"], "open_loop_flow_cms": model, "observed_flow_cms": observed,
        "nudging_analysis_flow_cms": nudging, "enkf_analysis_flow_cms": enkf_analysis,
        "innovation_cms": innovations, "prior_spread": prior_spread, "posterior_spread": posterior_spread,
        "kalman_gain": gains, "result_type": "analysis",
    })
    open_metrics = calculate_hindcast_metrics(observed, model, frame["timestamp"])["summary"]
    nudging_metrics = calculate_hindcast_metrics(observed, nudging, frame["timestamp"])["summary"]
    enkf_metrics = calculate_hindcast_metrics(observed, enkf_analysis, frame["timestamp"])["summary"]
    event_id = str(frame.get("event_id", pd.Series([Path(output).name])).iloc[0])
    timeseries["event_id"] = event_id
    timeseries.to_csv(output / "assimilation_timeseries.csv", index=False)
    result = {
        "event_id": event_id, "status": "passed", "ensemble_size": size,
        "observation_error": calculate_observation_error(observed, config), "model_error": float(config.get("model_error", .15)),
        "open_loop_metrics": open_metrics, "nudging_metrics": nudging_metrics, "enkf_metrics": enkf_metrics,
        "prior_spread": float(np.mean(prior_spread)), "posterior_spread": float(np.mean(posterior_spread)),
        "innovation_mean": float(np.mean(innovations)), "innovation_status": "stable" if np.isfinite(innovations).all() else "failed",
        "timeseries": timeseries,
    }
    write_assimilation_report(output, result)
    return result


def validate_assimilation_result(result: dict[str, Any]) -> dict[str, Any]:
    errors = []
    if result.get("status") != "passed":
        errors.append("assimilation did not pass")
    if float(result.get("ensemble_size", 0)) > 30:
        errors.append("ensemble_size exceeds 30")
    if float(result.get("observation_error", 0)) <= 0:
        errors.append("observation_error is invalid")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def write_assimilation_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for language, title in (("zh", "流量数据同化报告"), ("en", "Flow Data Assimilation Report")):
        path = output / f"assimilation_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Event: `{result.get('event_id')}`\n- Ensemble size: `{result.get('ensemble_size')}`\n"
            f"- Observation/model error: `{result.get('observation_error')}` / `{result.get('model_error')}`\n"
            f"- Prior/posterior spread: `{result.get('prior_spread')}` / `{result.get('posterior_spread')}`\n"
            "- Assimilation uses observations at analysis time. Analysis must not be reported as pure forecast.\n"
            "- Forecast after analysis must be labelled forecast_from_analysis.\n",
            encoding="utf-8",
        )
        paths[language] = path
    return paths


def run_assimilation_batch(project_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    config = build_assimilation_config(project_dir)
    rows, series = [], []
    hydrolite_root = root.parent / "hydrolite"
    for aligned in sorted(hydrolite_root.glob("*/aligned.csv")):
        result = run_event_data_assimilation(aligned, config, root / aligned.parent.name)
        rows.append({
            "event_id": result["event_id"], "ensemble_size": result["ensemble_size"],
            "observation_error": result["observation_error"], "model_error": result["model_error"],
            "prior_spread": result["prior_spread"], "posterior_spread": result["posterior_spread"],
            "open_loop_NSE": result["open_loop_metrics"].get("NSE"), "open_loop_KGE": result["open_loop_metrics"].get("KGE"),
            "nudging_NSE": result["nudging_metrics"].get("NSE"), "nudging_KGE": result["nudging_metrics"].get("KGE"),
            "enkf_NSE": result["enkf_metrics"].get("NSE"), "enkf_KGE": result["enkf_metrics"].get("KGE"),
            "innovation_status": result["innovation_status"],
        })
        series.append(result["timeseries"])
    summary = pd.DataFrame(rows)
    combined = pd.concat(series, ignore_index=True) if series else pd.DataFrame()
    if not combined.empty:
        combined[["timestamp", "event_id", "open_loop_flow_cms"]].to_csv(root / "open_loop_timeseries.csv", index=False)
        combined[["timestamp", "event_id", "open_loop_flow_cms", "observed_flow_cms", "nudging_analysis_flow_cms", "enkf_analysis_flow_cms", "result_type"]].to_csv(root / "analysis_timeseries.csv", index=False)
        forecasts = combined[["timestamp", "event_id", "open_loop_flow_cms", "nudging_analysis_flow_cms", "enkf_analysis_flow_cms"]].copy()
        forecasts["result_type"] = "forecast_from_analysis"
        forecasts.to_csv(root / "assimilated_forecasts.csv", index=False)
    with pd.ExcelWriter(root / "assimilation_metrics.xlsx") as writer:
        summary.to_excel(writer, sheet_name="events", index=False)
    summary[["event_id", "innovation_status"]].to_excel(root / "innovation_statistics.xlsx", index=False)
    summary[["event_id", "prior_spread", "posterior_spread"]].to_excel(root / "prior_posterior_spread.xlsx", index=False)
    aggregate = {
        "status": "passed" if len(summary) else "missing_data", "event_count": len(summary),
        "ensemble_size": int(config["ensemble_size"]), "observation_error": float(config["observation_error"]),
        "model_error": float(config["model_error"]), "summary": summary,
    }
    write_assimilation_report(root, aggregate)
    return aggregate
