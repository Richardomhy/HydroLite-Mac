"""Transparent, dependency-light multi-horizon forecast baselines."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from hydrolite.metrics import kge, mae, nse, pbias, r2, rmse


HORIZONS = (1, 3, 6, 12)
MODES = {"persistence", "direct", "recursive", "direct_recursive_hybrid"}
BASELINES = {"persistence", "seasonal_climatology", "linear_autoregression", "linear_regression", "ridge_closed_form", "upstream_weighted_linear", "gamma_linear", "graph_linear", "graph_trend_linear"}


@dataclass(slots=True)
class LinearModel:
    coefficients: np.ndarray
    feature_names: list[str]
    intercept: bool = True
    ridge_alpha: float = 0.0

    def predict(self, features: Any) -> np.ndarray:
        values = np.asarray(features, dtype=float)
        if values.ndim == 1: values = values.reshape(1, -1)
        design = np.column_stack([np.ones(len(values)), values]) if self.intercept else values
        return np.maximum(0.0, design @ self.coefficients)


def build_forecast_horizons(horizons: Sequence[int] = HORIZONS) -> list[int]:
    values = sorted({int(value) for value in horizons})
    if not values or values[0] <= 0: raise ValueError("Forecast horizons must be positive timesteps")
    return values


def fit_linear_model(features: Any, target: Any, feature_names: Sequence[str] | None = None, ridge_alpha: float = 0.0, intercept: bool = True) -> LinearModel:
    x = np.asarray(features, dtype=float); y = np.asarray(target, dtype=float)
    if x.ndim == 1: x = x.reshape(-1, 1)
    mask = np.isfinite(y) & np.all(np.isfinite(x), axis=1); x, y = x[mask], y[mask]
    if not len(y): raise ValueError("No finite training samples")
    design = np.column_stack([np.ones(len(x)), x]) if intercept else x; penalty = np.eye(design.shape[1]) * float(ridge_alpha)
    if intercept: penalty[0, 0] = 0.0
    coefficients = np.linalg.pinv(design.T @ design + penalty) @ design.T @ y
    return LinearModel(coefficients, list(feature_names or [f"x{i}" for i in range(x.shape[1])]), intercept, float(ridge_alpha))


def build_direct_training_sets(features: Any, target: Any, horizons: Sequence[int] = HORIZONS, timestamps: Any | None = None) -> dict[int, dict[str, Any]]:
    x = pd.DataFrame(features).reset_index(drop=True); y = pd.Series(target, dtype=float).reset_index(drop=True); dates = pd.Series(pd.to_datetime(timestamps)) if timestamps is not None else pd.Series(pd.RangeIndex(len(y)))
    result = {}
    for horizon in build_forecast_horizons(horizons):
        valid = len(y) - horizon
        result[horizon] = {"features": x.iloc[:valid].copy(), "target": y.shift(-horizon).iloc[:valid].copy(), "issue_time": dates.iloc[:valid].copy(), "target_time": dates.shift(-horizon).iloc[:valid].copy(), "test_used_for_selection": False}
    return result


def fit_direct_models(features: Any, target: Any, horizons: Sequence[int] = HORIZONS, *, ridge_alpha: float = 1e-6, feature_names: Sequence[str] | None = None) -> dict[int, LinearModel]:
    sets = build_direct_training_sets(features, target, horizons); return {horizon: fit_linear_model(item["features"], item["target"], feature_names or list(pd.DataFrame(features).columns), ridge_alpha) for horizon, item in sets.items()}


def build_direct_forecast(models: Mapping[int, LinearModel], issue_features: Any) -> dict[int, float]:
    return {int(horizon): float(model.predict(issue_features)[0]) for horizon, model in models.items()}


def build_recursive_forecast(model: LinearModel, observed_history: Any, horizons: Sequence[int] = HORIZONS, *, lag_count: int | None = None) -> dict[str, Any]:
    """Forecast from a frozen issue-time history; future observations are never read."""
    history = list(np.asarray(observed_history, dtype=float)); lag_count = int(lag_count or len(model.feature_names)); maximum = max(build_forecast_horizons(horizons)); predictions: list[float] = []
    if len(history) < lag_count: raise ValueError("observed_history is shorter than the autoregressive lag count")
    for _ in range(maximum):
        features = np.asarray(history[-lag_count:][::-1], dtype=float); prediction = float(model.predict(features)[0]); predictions.append(prediction); history.append(prediction)
    return {"forecast": {int(h): predictions[int(h) - 1] for h in horizons}, "observed_history_count": len(observed_history), "predicted_history_count": len(predictions), "future_observations_used": False}


def build_hybrid_forecast(direct: Mapping[int, float], recursive: Mapping[int, float], weights: Mapping[int, Mapping[str, float]]) -> dict[int, float]:
    return {int(h): float(weights[int(h)]["direct"] * direct[int(h)] + weights[int(h)]["recursive"] * recursive[int(h)]) for h in direct}


def select_hybrid_weights(validation_direct: Mapping[int, Any], validation_recursive: Mapping[int, Any], validation_observed: Mapping[int, Any], method: str = "validation_inverse_error", validation_period: tuple[Any, Any] | None = None) -> dict[int, dict[str, Any]]:
    if method not in {"fixed_equal", "validation_inverse_error", "validation_optimized_simplex"}: raise ValueError(f"Unsupported hybrid weighting method: {method}")
    result = {}
    for horizon in sorted(validation_observed):
        y = np.asarray(validation_observed[horizon], dtype=float); direct = np.asarray(validation_direct[horizon], dtype=float); recursive = np.asarray(validation_recursive[horizon], dtype=float)
        if method == "fixed_equal": weight = 0.5
        elif method == "validation_inverse_error":
            errors = np.asarray([np.sqrt(np.nanmean((direct - y) ** 2)), np.sqrt(np.nanmean((recursive - y) ** 2))]); inverse = 1.0 / np.maximum(errors, 1e-12); weight = float(inverse[0] / inverse.sum())
        else:
            delta = direct - recursive; denominator = float(np.dot(delta, delta)); weight = float(np.clip(np.dot(y - recursive, delta) / denominator, 0.0, 1.0)) if denominator else 0.5
        result[int(horizon)] = {"direct": weight, "recursive": 1.0 - weight, "weight_fit_period": [str(item) for item in validation_period] if validation_period else "validation_only", "validation_metric": "RMSE", "method": method, "test_used_for_selection": False}
    return result


def evaluate_horizon(observed: Any, predicted: Any, horizon: int) -> dict[str, Any]:
    obs, pred = np.asarray(observed, dtype=float), np.asarray(predicted, dtype=float); mask = np.isfinite(obs) & np.isfinite(pred); obs, pred = obs[mask], pred[mask]
    if not len(obs): return {"horizon": int(horizon), **{name: np.nan for name in ("NSE", "KGE", "RMSE", "MAE", "PBIAS", "R2", "peak_error", "timing_error", "volume_error")}}
    return {"horizon": int(horizon), "NSE": float(nse(obs, pred)), "KGE": float(kge(obs, pred)), "RMSE": float(rmse(obs, pred)), "MAE": float(mae(obs, pred)), "PBIAS": float(pbias(obs, pred)), "R2": float(r2(obs, pred)), "peak_error": float(pred.max() - obs.max()), "timing_error": int(np.argmax(pred) - np.argmax(obs)), "volume_error": float(pred.sum() - obs.sum())}


def evaluate_all_horizons(observed: Mapping[int, Any], predictions: Mapping[int, Any], model: str = "model") -> pd.DataFrame:
    return pd.DataFrame([{**evaluate_horizon(observed[h], predictions[h], h), "model": model} for h in sorted(predictions)])


def calculate_error_growth(metrics: Any) -> pd.DataFrame:
    frame = pd.DataFrame(metrics).sort_values("horizon").copy(); base = frame.iloc[0]
    frame["error_growth"] = frame.RMSE - float(base.RMSE); frame["bias_growth"] = frame.PBIAS.abs() - abs(float(base.PBIAS)); frame["variance_growth"] = frame.RMSE.pow(2) - float(base.RMSE) ** 2
    return frame[["model", "horizon", "RMSE", "error_growth", "bias_growth", "variance_growth"]] if "model" in frame else frame[["horizon", "RMSE", "error_growth", "bias_growth", "variance_growth"]]


def calculate_horizon_skill_decay(metrics: Any) -> pd.DataFrame:
    frame = pd.DataFrame(metrics).sort_values("horizon").copy(); reference = float(frame.iloc[0].NSE); frame["skill_decay"] = reference - frame.NSE; return frame[[column for column in ("model", "horizon", "NSE", "skill_decay") if column in frame]]


def validate_multihorizon_result(result: Mapping[str, Any]) -> dict[str, Any]:
    weights = result.get("weights", {}); invalid = []
    for horizon, row in weights.items():
        values = [float(row.get("direct", -1)), float(row.get("recursive", -1))]
        if min(values) < 0 or not np.isclose(sum(values), 1.0): invalid.append(int(horizon))
        if row.get("test_used_for_selection"): invalid.append(int(horizon))
    future = bool(result.get("future_observations_used", False))
    return {"status": "passed" if not invalid and not future else "failed", "invalid_weight_horizons": sorted(set(invalid)), "future_observations_used": future, "validation_only_weighting_gate": not invalid, "test_selection_leakage": bool(invalid)}


def calculate_horizon_diversity(predictions: Mapping[int, Any]) -> float:
    arrays = [np.asarray(item, dtype=float) for item in predictions.values()]; common = min(map(len, arrays)); return float(np.nanmean(np.nanstd(np.vstack([item[:common] for item in arrays]), axis=0)))


def write_multihorizon_report(metrics: Any, predictions: Any, weights: Any, output_dir: str | Path) -> dict[str, Path]:
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); metric_frame = pd.DataFrame(metrics); prediction_frame = pd.DataFrame(predictions)
    metrics_path = root / "horizon_metrics.xlsx"; error_path = root / "error_growth.xlsx"; prediction_path = root / "horizon_predictions.csv"
    with pd.ExcelWriter(metrics_path) as writer:
        metric_frame.to_excel(writer, sheet_name="per_horizon_metrics", index=False); metric_frame.groupby("model", as_index=False).mean(numeric_only=True).to_excel(writer, sheet_name="aggregate_metrics", index=False)
    calculate_error_growth(metric_frame).to_excel(error_path, index=False); prediction_frame.to_csv(prediction_path, index=False)
    (root / "multihorizon_manifest.json").write_text(json.dumps({"horizons": sorted(metric_frame.horizon.unique().tolist()), "weights": weights, "test_used_for_selection": False}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"metrics": metrics_path, "error_growth": error_path, "predictions": prediction_path}


# Compatibility names used by the prior skeleton.
def generate_direct_forecasts(series: Any, horizons: Sequence[int] = HORIZONS) -> dict[int, np.ndarray]:
    return {int(h): pd.Series(series).shift(int(h)).to_numpy() for h in horizons}


def generate_recursive_forecasts(series: Any, horizons: Sequence[int] = HORIZONS) -> dict[int, np.ndarray]:
    return generate_direct_forecasts(series, horizons)


def optimize_blend_on_validation(physical: Any, persistence: Any, observed: Any) -> dict[str, float | str | bool]:
    selected = select_hybrid_weights({1: physical}, {1: persistence}, {1: observed}, "validation_optimized_simplex")[1]
    return {"physical_weight": float(selected["direct"]), "persistence_weight": float(selected["recursive"]), "fit_data": "validation_only", "test_used_for_selection": False}


def blend_horizon_forecasts(physical: Any, persistence: Any, weights: Mapping[str, float]) -> np.ndarray:
    return float(weights["physical_weight"]) * np.asarray(physical) + float(weights["persistence_weight"]) * np.asarray(persistence)
