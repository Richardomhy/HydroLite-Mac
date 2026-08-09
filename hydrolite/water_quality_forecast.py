"""Transparent multi-station water-quality forecast baselines."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from hydrolite.multihorizon_forecast import fit_linear_model
from hydrolite.water_quality_contracts import HORIZONS_DAYS
from hydrolite.water_quality_evaluation import build_empirical_uncertainty, calculate_water_quality_metrics


CANDIDATE_MODELS = {
    "persistence": [],
    "seasonal_climatology": ["season_sin", "season_cos"],
    "station_local_linear": ["local_lag_1", "local_lag_3", "local_lag_7", "local_rolling_7"],
    "local_hydrology_linear": ["local_lag_1", "flow_cms", "rainfall_mm", "surface_runoff", "interflow", "baseflow"],
    "local_gamma_linear": ["local_lag_1", "gamma_fast", "gamma_medium", "gamma_slow"],
    "upstream_weighted_linear": ["local_lag_1", "upstream_lag_1_mean"],
    "graph_hydrology_linear": ["local_lag_1", "upstream_lag_1_mean", "flow_cms", "rainfall_mm", "surface_runoff", "interflow", "baseflow"],
    "graph_gamma_linear": ["local_lag_1", "upstream_lag_1_mean", "gamma_fast", "gamma_medium", "gamma_slow"],
    "graph_gamma_trend_linear": ["local_lag_1", "upstream_lag_1_mean", "gamma_fast", "gamma_medium", "gamma_slow", "causal_trend_7"],
}


def split_by_time(data: Any, train_fraction: float = 0.6, validation_fraction: float = 0.2) -> pd.DataFrame:
    frame = pd.DataFrame(data).copy(); dates = sorted(pd.to_datetime(frame.timestamp).dropna().unique())
    if len(dates) < 10: raise ValueError("At least 10 timestamps are required")
    train_end = dates[max(0, int(len(dates) * train_fraction) - 1)]; validation_end = dates[max(1, int(len(dates) * (train_fraction + validation_fraction)) - 1)]
    frame["split"] = np.where(frame.timestamp <= train_end, "train", np.where(frame.timestamp <= validation_end, "validation", "test"))
    return frame


def build_forecast_samples(features: Any, horizons: Sequence[int] = HORIZONS_DAYS) -> pd.DataFrame:
    frame = pd.DataFrame(features).copy().sort_values(["station_id", "variable_id", "timestamp"])
    parts = []
    for horizon in sorted(set(map(int, horizons))):
        shifted = frame.groupby(["station_id", "variable_id"], sort=False)["value"].shift(-horizon)
        valid_time = frame.groupby(["station_id", "variable_id"], sort=False)["timestamp"].shift(-horizon)
        item = frame.copy(); item["observed"] = shifted; item["valid_time"] = valid_time; item["horizon_days"] = horizon; item["horizon_status"] = "long_horizon_diagnostic" if horizon == 14 else "forecast_experiment"
        parts.append(item[item.observed.notna()])
    return split_by_time(pd.concat(parts, ignore_index=True))


def _matrix(frame: pd.DataFrame, columns: Sequence[str], fit_medians: Mapping[str, float] | None = None) -> tuple[np.ndarray, dict[str, float], list[str]]:
    columns = [column for column in columns if column in frame]
    numeric = frame[columns].apply(pd.to_numeric, errors="coerce") if columns else pd.DataFrame(index=frame.index)
    stations = pd.get_dummies(frame.station_id.astype(str), prefix="station", dtype=float)
    matrix = pd.concat([numeric, stations], axis=1)
    medians = dict(fit_medians or {column: float(matrix[column].median()) if matrix[column].notna().any() else 0.0 for column in matrix})
    for column in medians:
        if column not in matrix: matrix[column] = 0.0
    matrix = matrix.reindex(columns=list(medians)).fillna(pd.Series(medians))
    return matrix.to_numpy(dtype=float), medians, list(matrix.columns)


def fit_candidate_models(samples: Any, candidates: Mapping[str, Sequence[str]] | None = None, ridge_alpha: float = 1e-6) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = pd.DataFrame(samples).copy(); candidates = dict(candidates or CANDIDATE_MODELS); prediction_parts = []; metrics = []; selections = []
    for (variable, horizon), group in frame.groupby(["variable_id", "horizon_days"], sort=False):
        candidate_predictions: dict[str, pd.DataFrame] = {}
        for model_id, columns in candidates.items():
            if model_id == "graph_gamma_trend_linear" and "causal_trend_7" not in group:
                continue
            train = group[group.split == "train"].copy(); validation = group[group.split == "validation"].copy(); test = group[group.split == "test"].copy()
            if model_id == "persistence":
                for subset in (train, validation, test): subset["predicted"] = subset["local_lag_1"]
            elif model_id == "seasonal_climatology":
                climatology = train.assign(month=train.timestamp.dt.month).groupby(["station_id", "month"])["observed"].mean()
                global_mean = float(train.observed.mean())
                for subset in (train, validation, test): subset["predicted"] = [climatology.get((station, timestamp.month), global_mean) for station, timestamp in zip(subset.station_id, subset.timestamp)]
            else:
                x_train, medians, names = _matrix(train, columns)
                model = fit_linear_model(x_train, train.observed.to_numpy(), names, ridge_alpha)
                for subset in (train, validation, test): subset["predicted"] = model.predict(_matrix(subset, columns, medians)[0])
            combined = pd.concat([train, validation, test], ignore_index=True)
            combined["model_id"] = model_id
            candidate_predictions[model_id] = combined
            for split_name, subset in combined.groupby("split"):
                metrics.append({"variable_id": variable, "horizon_days": int(horizon), "model_id": model_id, "split": split_name, "sample_count": len(subset), **calculate_water_quality_metrics(subset.observed, subset.predicted)})
        metric_frame = pd.DataFrame(metrics)
        current = metric_frame[(metric_frame.variable_id == variable) & (metric_frame.horizon_days == horizon) & (metric_frame.split == "validation")]
        selected = str(current.sort_values(["RMSE", "MAE", "model_id"]).iloc[0].model_id)
        selected_predictions = candidate_predictions[selected].copy()
        validation = selected_predictions[selected_predictions.split == "validation"]
        lower, upper, uncertainty = build_empirical_uncertainty(validation.observed, validation.predicted, selected_predictions.predicted)
        selected_predictions["lower"] = lower; selected_predictions["upper"] = upper; selected_predictions["uncertainty_type"] = uncertainty["uncertainty_type"]
        selected_predictions["selected_model"] = True; prediction_parts.append(selected_predictions)
        selected_metric = current[current.model_id == selected].iloc[0]
        selections.append({"variable_id": variable, "horizon_days": int(horizon), "candidate_models": ",".join(sorted(candidate_predictions)), "selected_model": selected, "selection_metric": "validation_RMSE", "validation_RMSE": float(selected_metric.RMSE), "selection_reason": "lowest validation RMSE with deterministic tie-break", "test_used": False, "test_used_for_selection": False, "uncertainty_fit": "validation_only", "horizon_status": "long_horizon_diagnostic" if int(horizon) == 14 else "forecast_experiment"})
    return pd.concat(prediction_parts, ignore_index=True), pd.DataFrame(metrics), pd.DataFrame(selections)


def calculate_feature_ablation(candidate_metrics: Any) -> pd.DataFrame:
    frame = pd.DataFrame(candidate_metrics); test = frame[frame.split == "test"].copy(); baseline = test[test.model_id == "station_local_linear"][["variable_id", "horizon_days", "RMSE"]].rename(columns={"RMSE": "baseline_RMSE"})
    result = test.merge(baseline, on=["variable_id", "horizon_days"], how="left")
    result["RMSE_improvement"] = result.baseline_RMSE - result.RMSE
    result["feature_group_value_added"] = np.where(result.RMSE_improvement > 0, "demonstrated_synthetic", "not_demonstrated")
    result["real_data_value_added"] = "not_tested"
    return result


def validate_forecast_result(predictions: Any, selections: Any) -> dict[str, Any]:
    frame = pd.DataFrame(predictions); selected = pd.DataFrame(selections)
    leaked = bool(selected.test_used_for_selection.astype(bool).any()) if len(selected) else True
    future = bool((pd.to_datetime(frame.timestamp) >= pd.to_datetime(frame.valid_time)).any()) if len(frame) else True
    missing = sorted({1, 3, 7, 14} - set(frame.horizon_days.astype(int))) if len(frame) else [1, 3, 7, 14]
    return {"status": "passed" if not leaked and not future and not missing else "failed", "test_used_for_selection": leaked, "future_context_leakage": future, "missing_horizons": missing, "nonnegative_predictions": bool((frame.predicted >= 0).all()) if len(frame) else False}


def select_water_quality_model_on_validation(candidate_metrics: Any) -> pd.DataFrame:
    frame = pd.DataFrame(candidate_metrics); validation = frame[frame.split == "validation"].copy(); selected = validation.sort_values(["variable_id", "horizon_days", "RMSE", "MAE", "model_id"]).groupby(["variable_id", "horizon_days"], as_index=False).first(); return selected.rename(columns={"model_id": "selected_model", "RMSE": "validation_RMSE"}).assign(validation_metric="RMSE", selection_reason="lowest validation RMSE", test_used=False)
