"""Evaluation helpers for experimental water-quality forecasts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _paired(observed: Any, predicted: Any) -> tuple[np.ndarray, np.ndarray]:
    obs = np.asarray(observed, dtype=float); pred = np.asarray(predicted, dtype=float)
    mask = np.isfinite(obs) & np.isfinite(pred)
    return obs[mask], pred[mask]


def calculate_water_quality_metrics(observed: Any, predicted: Any) -> dict[str, float]:
    obs, pred = _paired(observed, predicted)
    if not len(obs):
        return {name: np.nan for name in ("RMSE", "MAE", "R2", "NSE", "KGE", "PBIAS", "Spearman", "bias", "relative_error", "peak_error", "peak_timing_error", "high_value_recall", "low_value_bias")}
    residual = pred - obs; mean_obs = float(np.mean(obs)); denominator = float(np.sum((obs - mean_obs) ** 2))
    r = float(np.corrcoef(obs, pred)[0, 1]) if len(obs) > 1 and np.std(obs) > 0 and np.std(pred) > 0 else np.nan
    alpha = float(np.std(pred) / np.std(obs)) if np.std(obs) > 0 else np.nan
    beta = float(np.mean(pred) / mean_obs) if mean_obs != 0 else np.nan
    high = obs >= np.quantile(obs, 0.9); low = obs <= np.quantile(obs, 0.1)
    return {
        "RMSE": float(np.sqrt(np.mean(residual ** 2))),
        "MAE": float(np.mean(np.abs(residual))),
        "R2": float(r ** 2) if np.isfinite(r) else np.nan,
        "NSE": float(1 - np.sum(residual ** 2) / denominator) if denominator else np.nan,
        "KGE": float(1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)) if all(np.isfinite([r, alpha, beta])) else np.nan,
        "PBIAS": float(100 * np.sum(residual) / np.sum(obs)) if np.sum(obs) else np.nan,
        "Spearman": float(pd.Series(obs).corr(pd.Series(pred), method="spearman")) if len(obs) > 1 else np.nan,
        "bias": float(np.mean(residual)),
        "relative_error": float(np.mean(np.abs(residual) / np.maximum(np.abs(obs), 1e-9))),
        "peak_error": float(pred.max() - obs.max()),
        "peak_timing_error": float(np.argmax(pred) - np.argmax(obs)),
        "high_value_recall": float(np.mean(pred[high] >= np.quantile(obs, 0.9))) if high.any() else np.nan,
        "low_value_bias": float(np.mean(residual[low])) if low.any() else np.nan,
    }


def calculate_threshold_diagnostics(observed: Any, predicted: Any, threshold: float) -> dict[str, float]:
    obs, pred = _paired(observed, predicted)
    actual = obs >= float(threshold); forecast = pred >= float(threshold)
    tp = int(np.sum(actual & forecast)); fp = int(np.sum(~actual & forecast)); fn = int(np.sum(actual & ~forecast)); tn = int(np.sum(~actual & ~forecast))
    precision = tp / (tp + fp) if tp + fp else np.nan; recall = tp / (tp + fn) if tp + fn else np.nan
    return {"diagnostic_threshold": float(threshold), "true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn, "precision": precision, "recall": recall, "F1": 2 * precision * recall / (precision + recall) if precision + recall else np.nan, "false_alarm_rate": fp / (fp + tn) if fp + tn else np.nan, "threshold_type": "diagnostic_only"}


def build_empirical_uncertainty(validation_observed: Any, validation_predicted: Any, predictions: Any, alpha: float = 0.1) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    obs, pred = _paired(validation_observed, validation_predicted); residual = obs - pred
    lower_q, upper_q = (np.quantile(residual, alpha / 2), np.quantile(residual, 1 - alpha / 2)) if len(residual) else (np.nan, np.nan)
    forecast = np.asarray(predictions, dtype=float)
    return np.maximum(0.0, forecast + lower_q), np.maximum(0.0, forecast + upper_q), {"uncertainty_type": "empirical_validation_residual_interval", "alpha": alpha, "fit_data": "validation_only", "test_used": False, "residual_count": len(residual)}


def evaluate_prediction_table(predictions: Any) -> pd.DataFrame:
    frame = pd.DataFrame(predictions); rows = []
    for keys, group in frame.groupby(["variable_id", "horizon_days", "model_id", "split"], dropna=False):
        variable, horizon, model, split = keys
        rows.append({"variable_id": variable, "horizon_days": int(horizon), "model_id": model, "split": split, "sample_count": len(group), **calculate_water_quality_metrics(group.observed, group.predicted)})
    return pd.DataFrame(rows)


def evaluate_load_predictions(predictions: Any) -> pd.DataFrame:
    frame = pd.DataFrame(predictions)
    if not {"observed_load_kg_day", "predicted_load_kg_day"}.issubset(frame):
        return pd.DataFrame(columns=["variable_id", "horizon_days", "model_id", "load_status"])
    rows = []
    for keys, group in frame.groupby(["variable_id", "horizon_days", "model_id"]):
        rows.append({"variable_id": keys[0], "horizon_days": keys[1], "model_id": keys[2], "load_status": "available" if group.observed_load_kg_day.notna().any() else "unavailable", **calculate_water_quality_metrics(group.observed_load_kg_day, group.predicted_load_kg_day)})
    return pd.DataFrame(rows)


def validate_evaluation_separation(model_selection: Any, predictions: Any) -> dict[str, Any]:
    selection = pd.DataFrame(model_selection); frame = pd.DataFrame(predictions)
    leaked = bool(selection.get("test_used_for_selection", pd.Series(False, index=selection.index)).astype(bool).any())
    missing_splits = sorted({"train", "validation", "test"} - set(frame.get("split", [])))
    return {"status": "passed" if not leaked and not missing_splits else "failed", "test_used_for_selection": leaked, "missing_splits": missing_splits}
