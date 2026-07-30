from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hydrolite.ml_forecast import evaluate_ml_forecast, predict_ml_model, train_linear_model, train_ridge_model


def assess_hybrid_real_data_readiness(workspace_dir: str | Path) -> dict[str, Any]:
    from hydrolite.validation_readiness import assess_ml_validation_readiness
    result = assess_ml_validation_readiness(workspace_dir)
    return {
        "status": "ready" if result["real_training_ready"] else "blocked",
        "real_training_ready": result["real_training_ready"],
        "physics_water_balance_required": True,
        "reason": "Requires five real qualified events, 500 valid steps, independent validation, and no future leakage.",
    }


def build_physics_residual_target(observed, physics) -> np.ndarray:
    return np.asarray(observed, float) - np.asarray(physics, float)


def train_residual_correction_model(features: pd.DataFrame, residual, config: dict[str, Any]) -> dict[str, Any]:
    data = features.copy()
    data["residual_target"] = np.asarray(residual, float)
    spec = {**config, "target": "residual_target"}
    return train_ridge_model(data, spec) if config.get("method") == "ridge" else train_linear_model(data, spec)


def apply_residual_correction(physics_forecast, residual_forecast) -> np.ndarray:
    return enforce_nonnegative_flow(np.asarray(physics_forecast, float) + np.asarray(residual_forecast, float))


def enforce_nonnegative_flow(forecast) -> np.ndarray:
    return np.maximum(np.asarray(forecast, float), 0)


def check_hybrid_water_balance_limits(result: dict[str, Any]) -> dict[str, Any]:
    change = abs(float(result.get("volume_change_percent", 0)))
    return {"status": "passed" if change <= float(result.get("limit_percent", 20)) else "needs_review", "volume_change_percent": change}


def evaluate_hybrid_forecast(observed, hybrid) -> dict[str, float]:
    return evaluate_ml_forecast(observed, hybrid)


def write_hybrid_model_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = root / "hybrid_model_report.md"
    metrics = root / "hybrid_model_metrics.xlsx"
    report.write_text(f"# Physics-data hybrid demo\n\nStatus: `{result.get('status')}`.\n\nThis is a synthetic residual-correction smoke test, not an observed calibration.\n", encoding="utf-8")
    pd.DataFrame([result]).to_excel(metrics, index=False)
    return {"report": report, "metrics": metrics}


def run_hybrid_synthetic_demo(data_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    data = pd.read_csv(data_path)
    train = data.iloc[:-120].copy()
    test = data.iloc[-120:].copy()
    features = ["hydrolite_flow_cms", "rainfall_mm"]
    residual = build_physics_residual_target(train["flow_cms"], train["hydrolite_flow_cms"])
    model = train_residual_correction_model(train[features], residual, {"features": features, "method": "linear"})
    correction = predict_ml_model(model, test[features])
    hybrid = apply_residual_correction(test["hydrolite_flow_cms"], correction)
    result = {"status": "passed", "model_id": "hybrid_physics_ml", "validation_level": "synthetic_demo", **evaluate_hybrid_forecast(test["flow_cms"], hybrid)}
    write_hybrid_model_report(output_dir, result)
    return result
