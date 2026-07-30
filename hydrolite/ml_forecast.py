from __future__ import annotations

from importlib.util import find_spec
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd


def detect_ml_dependencies() -> dict[str, Any]:
    return {
        "numpy": True,
        "pandas": True,
        "scikit_learn": find_spec("sklearn") is not None,
        "joblib": find_spec("joblib") is not None,
    }


def assess_ml_data_readiness(project_dir: str | Path, target: str | None = None) -> dict[str, Any]:
    project = Path(project_dir).expanduser().resolve()
    observed = list(project.glob("data/*observed*flow*.csv"))
    return {
        "status": "insufficient_multi_event_data",
        "real_training_ready": False,
        "continuous_steps_required": 500,
        "independent_events_required": 5,
        "independent_test_events_required": 1,
        "observed_files": [path.name for path in observed],
        "target": target or "outlet_flow_cms",
        "note": "Software gate only; it is not a scientific sufficiency standard.",
    }


def build_ml_features(data: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = config or {}
    frame = data.copy()
    rain = pd.to_numeric(frame[cfg.get("rainfall_column", "rainfall_mm")], errors="raise")
    frame["recent_rainfall_mm"] = rain.rolling(3, min_periods=1).sum()
    frame["cumulative_rainfall_mm"] = rain.groupby(frame.get("event_id", pd.Series("event", index=frame.index))).cumsum()
    frame["rainfall_intensity_mm_hr"] = rain
    frame["previous_discharge_cms"] = pd.to_numeric(frame[cfg.get("target", "flow_cms")], errors="raise").shift(1)
    frame["lead_time_hr"] = pd.to_numeric(frame.get("lead_time_hr", 1), errors="coerce").fillna(1)
    return frame


def detect_feature_leakage(data: pd.DataFrame, feature_spec: list[str] | dict[str, Any]) -> dict[str, Any]:
    features = list(feature_spec) if isinstance(feature_spec, list) else list(feature_spec.get("features", []))
    blocked = [
        name
        for name in features
        if name.lower().startswith(("future_flow", "future_discharge", "future_rain", "target_"))
    ]
    return {"status": "passed" if not blocked else "failed", "leaking_features": blocked}


def validate_feature_timestamps(data: pd.DataFrame) -> dict[str, Any]:
    column = "timestamp" if "timestamp" in data else "valid_time"
    values = pd.to_datetime(data[column], errors="coerce")
    return {"status": "passed" if values.notna().all() and values.is_monotonic_increasing else "failed"}


def split_time_series_data(data: pd.DataFrame, config: dict[str, Any] | None = None) -> dict[str, pd.DataFrame]:
    cfg = config or {}
    method = cfg.get("method", "chronological_holdout")
    if method not in {"chronological_holdout", "rolling_origin", "expanding_window", "event_based_split"}:
        raise ValueError(f"Unsupported time-series split: {method}")
    if method == "event_based_split" and "event_id" in data:
        events = list(dict.fromkeys(data["event_id"].astype(str)))
        test_event = events[-1]
        train = data[data["event_id"].astype(str) != test_event]
        test = data[data["event_id"].astype(str) == test_event]
    else:
        cut = max(1, min(len(data) - 1, int(len(data) * float(cfg.get("train_fraction", 0.8)))))
        train, test = data.iloc[:cut], data.iloc[cut:]
    return {"train": train.copy(), "test": test.copy(), "method": method}


def train_persistence_model(data: pd.DataFrame, config: dict[str, Any] | None = None) -> dict[str, Any]:
    target = (config or {}).get("target", "flow_cms")
    return {"model_id": "persistence_forecast", "status": "passed", "last_value": float(data[target].iloc[-1]), "target": target}


def train_linear_model(data: pd.DataFrame, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    features = cfg.get("features", ["hydrolite_flow_cms", "rainfall_mm"])
    target = cfg.get("target", "flow_cms")
    clean = data[features + [target]].dropna()
    design = np.column_stack([np.ones(len(clean)), clean[features].to_numpy(float)])
    coefficients, *_ = np.linalg.lstsq(design, clean[target].to_numpy(float), rcond=None)
    return {"model_id": "linear_regression_forecast", "status": "passed", "features": features, "target": target, "coefficients": coefficients.tolist()}


def _train_sklearn(data: pd.DataFrame, config: dict[str, Any], kind: str) -> dict[str, Any]:
    if find_spec("sklearn") is None:
        return {"model_id": kind, "status": "unavailable_optional", "reason": "scikit-learn is not installed"}
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    features = config.get("features", ["hydrolite_flow_cms", "rainfall_mm"])
    target = config.get("target", "flow_cms")
    constructors = {
        "ridge_regression_forecast": lambda: Ridge(alpha=1.0),
        "random_forest_forecast": lambda: RandomForestRegressor(n_estimators=20, max_depth=5, random_state=42),
        "gradient_boosting_forecast": lambda: GradientBoostingRegressor(n_estimators=30, max_depth=2, random_state=42),
    }
    model = constructors[kind]()
    model.fit(data[features], data[target])
    return {"model_id": kind, "status": "passed", "model": model, "features": features, "target": target}


def train_ridge_model(data: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    return _train_sklearn(data, config, "ridge_regression_forecast")


def train_random_forest_model(data: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    return _train_sklearn(data, config, "random_forest_forecast")


def train_gradient_boosting_model(data: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    return _train_sklearn(data, config, "gradient_boosting_forecast")


def predict_ml_model(model: dict[str, Any], features: pd.DataFrame) -> np.ndarray:
    if model["model_id"] == "persistence_forecast":
        return np.full(len(features), model["last_value"], dtype=float)
    if model["model_id"] == "linear_regression_forecast":
        design = np.column_stack([np.ones(len(features)), features[model["features"]].to_numpy(float)])
        return design @ np.asarray(model["coefficients"])
    return np.asarray(model["model"].predict(features[model["features"]]), dtype=float)


def evaluate_ml_forecast(observed: pd.Series | np.ndarray, predicted: pd.Series | np.ndarray) -> dict[str, float]:
    obs, pred = np.asarray(observed, float), np.asarray(predicted, float)
    error = pred - obs
    rmse = float(np.sqrt(np.mean(error**2)))
    mae = float(np.mean(np.abs(error)))
    denominator = float(np.sum((obs - obs.mean()) ** 2))
    nse = float(1 - np.sum(error**2) / denominator) if denominator else np.nan
    pbias = float(100 * np.sum(error) / np.sum(obs)) if np.sum(obs) else np.nan
    r2 = float(np.corrcoef(obs, pred)[0, 1] ** 2) if len(obs) > 1 else np.nan
    return {"RMSE": rmse, "MAE": mae, "NSE": nse, "KGE": np.nan, "PBIAS": pbias, "R2": r2, "peak_error": float(pred.max() - obs.max())}


def save_ml_model_metadata(output_dir: str | Path, result: dict[str, Any]) -> Path:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "ml_model_metadata.json"
    safe = {key: value for key, value in result.items() if key != "model"}
    path.write_text(json.dumps(safe, indent=2, default=str), encoding="utf-8")
    return path


def run_ml_synthetic_demo(data_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    started = time.perf_counter()
    data = pd.read_csv(data_path, parse_dates=["timestamp"])
    features = build_ml_features(data).dropna().reset_index(drop=True)
    split = split_time_series_data(features, {"method": "event_based_split"})
    config = {"features": ["hydrolite_flow_cms", "rainfall_mm", "recent_rainfall_mm"], "target": "flow_cms"}
    models = [train_persistence_model(split["train"], config), train_linear_model(split["train"], config)]
    rows = []
    for model in models:
        prediction = predict_ml_model(model, split["test"])
        rows.append({"model_id": model["model_id"], "status": model["status"], **evaluate_ml_forecast(split["test"]["flow_cms"], prediction)})
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(root / "ml_model_summary.xlsx", index=False)
    (root / "feature_manifest.json").write_text(json.dumps({"features": config["features"], "split": "event_based_split", "shuffle": False, "synthetic_demo": True}, indent=2), encoding="utf-8")
    return {"status": "passed", "model_count": len(rows), "metrics": rows, "runtime_seconds": time.perf_counter() - started}
