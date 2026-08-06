from __future__ import annotations

from importlib.util import find_spec
import json
from pathlib import Path
from typing import Any

import pandas as pd


def _model(model_id: str, zh: str, en: str, family: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "display_name_zh": zh,
        "display_name_en": en,
        "domain": "flood_forecast",
        "model_family": family,
        "implementation": extra.pop("implementation", model_id),
        "status": status,
        "dependency_status": "available",
        "input_schema": extra.pop("input_schema", "forecast rainfall and hydrologic state"),
        "output_schema": extra.pop("output_schema", "member time series and metrics"),
        "training_required": extra.pop("training_required", False),
        "calibration_required": extra.pop("calibration_required", False),
        "uncertainty_support": extra.pop("uncertainty_support", True),
        "reservoir_support": extra.pop("reservoir_support", False),
        "forecast_support": extra.pop("forecast_support", True),
        "limitations": extra.pop("limitations", ""),
        "documentation": extra.pop("documentation", "docs/flood_forecast_mvp.md"),
        "version": "0.7.0-dev",
        **extra,
    }


_MODELS = {
    row["model_id"]: row
    for row in [
        _model("hydrolite_event_model", "HydroLite 事件模型", "HydroLite event model", "physical", "available"),
        _model("hec_hms_event_model", "HEC-HMS 事件模型", "HEC-HMS event model", "physical", "available_local", implementation="HEC-HMS 4.13"),
        _model("hydrolite_reservoir_model", "HydroLite 水库模型", "HydroLite reservoir model", "physical", "available_demo", reservoir_support=True),
        _model("hec_hms_reservoir_model", "HEC-HMS 水库模型", "HEC-HMS reservoir model", "physical", "blocked_gate", reservoir_support=True, limitations="Reservoir compute gate is not verified."),
        _model("persistence_forecast", "持续性基线", "Persistence forecast", "statistical", "available"),
        _model("linear_regression_forecast", "线性回归基线", "Linear regression baseline", "machine_learning", "available", training_required=True),
        _model("ridge_regression_forecast", "岭回归", "Ridge regression", "machine_learning", "optional", training_required=True),
        _model("random_forest_forecast", "随机森林", "Random forest", "machine_learning", "optional", training_required=True),
        _model("gradient_boosting_forecast", "梯度提升", "Gradient boosting", "machine_learning", "optional", training_required=True),
        _model("lstm_rainfall_runoff", "LSTM 降雨径流", "LSTM rainfall-runoff", "deep_learning", "optional", training_required=True),
        _model("lstm_residual_correction", "LSTM 残差订正", "LSTM residual correction", "deep_learning", "optional", training_required=True),
        _model("hybrid_physics_ml", "物理-机器学习混合", "Physics-ML hybrid", "hybrid", "synthetic_demo", training_required=True),
        _model("hybrid_physics_lstm", "物理-LSTM 混合", "Physics-LSTM hybrid", "hybrid", "optional", training_required=True),
        _model("gamma_lag_feature_model", "Gamma 滞后特征", "Gamma lag feature model", "feature_engineering", "experimental", forecast_support=False, limitations="Causal feature engineering only; not a paper-model reproduction."),
        _model("physics_graph_residual_model", "物理图残差", "Physics graph residual", "hybrid_residual", "experimental", training_required=True, limitations="Physical water balance remains authoritative."),
        _model("causal_graph_temporal_model", "因果图时序", "Causal graph temporal", "graph_hydrology", "experimental", training_required=True, limitations="Bidirectional modes are blocked for future forecasts."),
        _model("trend_graph_water_quality_experiment", "趋势图水质实验", "Trend graph water-quality experiment", "graph_hydrology", "experimental", training_required=True, limitations="Water-quality production capability remains planned."),
        _model("hierarchical_multihorizon_model", "分层多提前期", "Hierarchical multihorizon", "multihorizon", "experimental", training_required=True),
        _model("flood_susceptibility_baseline", "洪水易发性基线", "Flood susceptibility baseline", "susceptibility", "experimental", training_required=True, forecast_support=False),
        _model("adaptive_flood_susceptibility_experiment", "自适应洪水易发性实验", "Adaptive flood susceptibility experiment", "experimental_rl", "experimental", training_required=True, forecast_support=False, limitations="Optional RL is not recommended without independent value added."),
    ]
}


def validate_model_spec(model_spec: dict[str, Any]) -> dict[str, Any]:
    required = {
        "model_id", "display_name_zh", "display_name_en", "domain", "model_family",
        "implementation", "status", "input_schema", "output_schema", "version",
    }
    missing = sorted(required - set(model_spec))
    return {"status": "passed" if not missing else "failed", "missing": missing}


def register_model(model_spec: dict[str, Any]) -> dict[str, Any]:
    check = validate_model_spec(model_spec)
    if check["status"] != "passed":
        raise ValueError(f"Invalid model spec; missing: {check['missing']}")
    _MODELS[model_spec["model_id"]] = dict(model_spec)
    return _MODELS[model_spec["model_id"]]


def list_models(domain: str | None = None) -> list[dict[str, Any]]:
    rows = [dict(row) for row in _MODELS.values()]
    return rows if domain is None else [row for row in rows if row["domain"] == domain]


def get_model(model_id: str) -> dict[str, Any]:
    if model_id not in _MODELS:
        raise KeyError(f"Unknown model_id: {model_id}")
    return dict(_MODELS[model_id])


def detect_model_dependencies(model_id: str) -> dict[str, Any]:
    if model_id in {"ridge_regression_forecast", "random_forest_forecast", "gradient_boosting_forecast"}:
        return {"dependency": "scikit-learn", "available": find_spec("sklearn") is not None}
    if model_id.startswith("lstm_") or model_id == "hybrid_physics_lstm":
        return {"dependency": "torch", "available": find_spec("torch") is not None}
    if model_id.startswith("hec_hms"):
        return {"dependency": "HEC-HMS 4.13", "available": Path("/Applications/HEC-HMS-4.13.app").exists()}
    return {"dependency": "core", "available": True}


def assess_model_readiness(model_id: str, project_dir: str | Path | None = None) -> dict[str, Any]:
    spec = get_model(model_id)
    dependency = detect_model_dependencies(model_id)
    if model_id == "hec_hms_reservoir_model":
        status = "blocked_gate"
    elif model_id.startswith("lstm_") and project_dir:
        status = "insufficient_data"
    elif not dependency["available"]:
        status = "unavailable_optional"
    else:
        status = spec["status"]
    return {"model_id": model_id, "status": status, "dependency": dependency, "project_dir": Path(project_dir).name if project_dir else None}


def get_available_models(context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    project = (context or {}).get("project_dir")
    return [{**row, "readiness": assess_model_readiness(row["model_id"], project)["status"]} for row in list_models()]


def write_model_registry_report(output_dir: str | Path) -> dict[str, Path]:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = get_available_models()
    xlsx = root / "model_registry.xlsx"
    report = root / "model_registry.md"
    manifest = root / "model_registry.json"
    pd.DataFrame(rows).to_excel(xlsx, index=False)
    report.write_text("# HydroLite model registry\n\n```text\n" + pd.DataFrame(rows)[["model_id", "status", "readiness"]].to_string(index=False) + "\n```\n", encoding="utf-8")
    manifest.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"xlsx": xlsx, "report": report, "json": manifest}
