from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time
from typing import Any
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from hydrolite.capability_registry import list_capabilities, write_capability_registry
from hydrolite.config import load_case
from hydrolite.forecast_contracts import normalize_rainfall_forecast, write_forecast_input_manifest
from hydrolite.forecast_rainfall import (
    create_multiplicative_scenarios,
    create_observed_replay_scenario,
    create_temporal_shift_scenarios,
    load_forecast_rainfall,
    validate_rainfall_ensemble,
    write_rainfall_ensemble,
)
from hydrolite.forecast_uncertainty import (
    calculate_ensemble_quantiles,
    calculate_exceedance_probability,
    calculate_peak_distribution,
    calculate_peak_time_distribution,
    calculate_reservoir_stage_distribution,
    calculate_volume_distribution,
    classify_uncertainty_sources,
    load_user_flood_thresholds,
)
from hydrolite.hybrid_forecast import run_hybrid_synthetic_demo
from hydrolite.hydrology import runoff_to_flow_cms
from hydrolite.io import read_reaches, read_subcatchments
from hydrolite.lstm_forecast import assess_lstm_data_readiness, detect_torch_environment, run_lstm_synthetic_smoke_test
from hydrolite.ml_forecast import assess_ml_data_readiness, detect_ml_dependencies, run_ml_synthetic_demo
from hydrolite.model_registry import get_available_models, write_model_registry_report
from hydrolite.reservoir_routing import (
    calculate_reservoir_event_metrics,
    load_reservoir_config,
    load_stage_area_volume_curve,
    load_stage_discharge_curve,
    route_reservoir_level_pool,
)
from hydrolite.routing import route_reaches
from hydrolite.water_balance import build_water_balance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "flood_forecast"
DEMO_PROJECT = ROOT / "projects" / "qgis_workflow_project"
DEMO_CONFIG = ROOT / "data_demo" / "flood_forecast" / "demo_forecast_config.yaml"
DEMO_RAINFALL = ROOT / "data_demo" / "flood_forecast" / "demo_rainfall_forecast.csv"
DEMO_ML = ROOT / "data_demo" / "flood_forecast" / "demo_ml_timeseries.csv"
DEMO_THRESHOLDS = ROOT / "data_demo" / "flood_forecast" / "demo_thresholds.yaml"


def _path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _case_file(project_dir: str | Path) -> Path:
    project = _path(project_dir)
    candidates = sorted((project / "cases").glob("*.yaml")) + sorted((project / "cases").glob("*.yml"))
    if candidates:
        baseline = [path for path in candidates if path.stem in {"qgis_demo", "demo"}]
        return baseline[0] if baseline else candidates[0]
    return ROOT / "cases" / "demo.yaml"


def create_flood_forecast_config(project_dir: str | Path, output_path: str | Path) -> Path:
    output = _path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "forecast_validation_level": "synthetic_demo",
        "forecast_mode": "hindcast_demo",
        "project_name": _path(project_dir).name,
        "rainfall_file": "data_demo/flood_forecast/demo_rainfall_forecast.csv",
        "threshold_file": "data_demo/flood_forecast/demo_thresholds.yaml",
        "maximum_members": 20,
        "hec_hms": {"enabled": False, "maximum_members": 5, "timeout_seconds": 120},
        "reservoir": {"enabled": True, "validation_level": "synthetic_demo"},
        "machine_learning": {"real_training": False, "synthetic_smoke_test": True},
        "lstm": {"real_training": False, "synthetic_smoke_test": True, "timeout_seconds": 120},
    }
    output.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return output


def load_flood_forecast_config(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(_path(path).read_text(encoding="utf-8")) or {}


def validate_flood_forecast_config(config: dict[str, Any]) -> dict[str, Any]:
    errors = []
    if int(config.get("maximum_members", 0)) not in range(1, 21):
        errors.append("maximum_members must be between 1 and 20")
    if config.get("forecast_validation_level") not in {"framework_only", "synthetic_demo", "hindcast_demo"}:
        errors.append("current MVP cannot claim a validation level above hindcast_demo")
    if int(config.get("hec_hms", {}).get("timeout_seconds", 120)) > 120:
        errors.append("HEC-HMS timeout must not exceed 120 seconds")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def assess_flood_forecast_readiness(project_dir: str | Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    project = _path(project_dir)
    water_gate_path = ROOT / "output" / "water_balance_audit" / "flood_forecast_gate.json"
    water_gate = json.loads(water_gate_path.read_text(encoding="utf-8")) if water_gate_path.exists() else {"water_balance_gate_passed": False}
    ml = assess_ml_data_readiness(project)
    torch = detect_torch_environment()
    return {
        "status": "ready_synthetic_demo" if water_gate.get("water_balance_gate_passed") else "blocked_water_balance",
        "forecast_validation_level": "synthetic_demo",
        "forecast_mode": "hindcast_demo",
        "hydrolite_water_balance_gate": bool(water_gate.get("water_balance_gate_passed")),
        "hydrolite_event_model": "available",
        "hec_hms_event_model": "available_local" if Path("/Applications/HEC-HMS-4.13.app").exists() else "unavailable_optional",
        "hydrolite_reservoir_model": "available_demo",
        "hec_hms_reservoir_model": "blocked_gate",
        "ml_real_data_readiness": ml["status"],
        "lstm_real_data_readiness": "insufficient_data",
        "torch": torch,
        "project_name": project.name,
        "limitations": [
            "Scenario ensemble and historical replay MVP only.",
            "No operational warning level is generated.",
            "Real multi-event validation and continuous initial states are unavailable.",
        ],
    }


def build_flood_forecast_plan(project_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": validate_flood_forecast_config(config)["status"],
        "project_name": _path(project_dir).name,
        "steps": ["rainfall_ensemble", "hydrolite_members", "optional_hec_hms_members", "hydrolite_reservoir", "optional_ml_lstm", "ensemble_quantiles", "reports"],
        "hec_hms_reservoir": "blocked_gate",
        "operational_forecast": False,
    }


def _member_rainfall(member: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"time": pd.to_datetime(member["valid_time"]), "rain_mm": member["precipitation_mm"].to_numpy(float)})


def _hydrology_metrics(result: pd.DataFrame, interval_minutes: float, issue_time: pd.Timestamp, balance_error: float) -> dict[str, Any]:
    peak_index = int(result["outflow_cms"].idxmax())
    peak_time = pd.to_datetime(result.loc[peak_index, "time"])
    values = result["outflow_cms"].to_numpy(float)
    weights = values / values.sum() if values.sum() else np.zeros_like(values)
    centroid = float(np.sum(np.arange(len(values)) * weights) * interval_minutes / 60)
    return {
        "peak_flow_cms": float(values.max()),
        "peak_time": peak_time,
        "time_to_peak_hr": float((peak_time - issue_time).total_seconds() / 3600),
        "runoff_volume_m3": float(values.sum() * interval_minutes * 60),
        "centroid_time_hr": centroid,
        "rising_limb_duration_hr": float(peak_index * interval_minutes / 60),
        "recession_limb_duration_hr": float((len(values) - peak_index - 1) * interval_minutes / 60),
        "water_balance_residual_percent": float(balance_error),
    }


def run_hydrolite_forecast_member(project_dir: str | Path, rainfall_member: pd.DataFrame, output_dir: str | Path) -> dict[str, Any]:
    started = time.perf_counter()
    member_id = str(rainfall_member["member_id"].iloc[0])
    output = _path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    case = load_case(_case_file(project_dir))
    rain = _member_rainfall(rainfall_member)
    interval_minutes = float(rainfall_member["interval_minutes"].iloc[0])
    dt_hours = interval_minutes / 60
    subcatchments = read_subcatchments(case.subcatchments_csv)
    reaches = read_reaches(case.reaches_csv)
    flow = runoff_to_flow_cms(rain, subcatchments, dt_hours)
    result = route_reaches(flow, reaches, dt_hours)
    _, outlet = build_water_balance(
        case_name=member_id,
        rainfall=rain,
        subcatchments=subcatchments,
        result=result,
        dt_hours=dt_hours,
    )
    balance_error = float(outlet["balance_error_percent"].iloc[0])
    issue_time = pd.to_datetime(rainfall_member["issue_time"].iloc[0])
    metrics = _hydrology_metrics(result, interval_minutes, issue_time, balance_error)
    frame = pd.DataFrame({
        "model_id": "hydrolite_event_model",
        "member_id": member_id,
        "issue_time": issue_time,
        "valid_time": pd.to_datetime(result["time"]),
        "lead_time_hr": (pd.to_datetime(result["time"]) - issue_time).dt.total_seconds() / 3600,
        "interval_minutes": interval_minutes,
        "outlet_flow_cms": result["outflow_cms"].to_numpy(float),
        "reservoir_inflow_cms": result["outflow_cms"].to_numpy(float),
        "reservoir_outflow_cms": np.nan,
        "reservoir_stage_m": np.nan,
        "reservoir_storage_m3": np.nan,
        "run_status": "success",
        "runtime_seconds": time.perf_counter() - started,
        "warnings": "",
    })
    frame.to_csv(output / "member_forecast.csv", index=False)
    return {"status": "success", "model_id": "hydrolite_event_model", "member_id": member_id, "timeseries": frame, "metrics": metrics, "runtime_seconds": time.perf_counter() - started, "output_dir": output}


def run_hec_hms_forecast_member(project_dir: str | Path, rainfall_member: pd.DataFrame, output_dir: str | Path, execute: bool = True) -> dict[str, Any]:
    member_id = str(rainfall_member["member_id"].iloc[0])
    output = _path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not execute:
        status, reason = "skipped_optional_local", "HEC-HMS member execution is disabled in the safe demo configuration."
    elif not Path("/Applications/HEC-HMS-4.13.app").exists():
        status, reason = "skipped_optional_dependency", "HEC-HMS 4.13 is unavailable."
    else:
        status, reason = "skipped_member_adapter_gate", "Member-specific DSS write/read-back must be verified before compute; no baseline result was reused."
    (output / "member_status.json").write_text(json.dumps({"member_id": member_id, "status": status, "reason": reason, "timeout_seconds": 120}, indent=2), encoding="utf-8")
    return {"status": status, "model_id": "hec_hms_event_model", "member_id": member_id, "reason": reason, "runtime_seconds": 0.0}


def run_hydrolite_reservoir_forecast(inflow: pd.DataFrame, reservoir_config: dict[str, Any] | str | Path, output_dir: str | Path) -> dict[str, Any]:
    config_path = _path(reservoir_config) if isinstance(reservoir_config, (str, Path)) else _path(reservoir_config["_config_path"])
    config = load_reservoir_config(config_path)
    base = config_path.parent
    stage_storage = load_stage_area_volume_curve(base / config["stage_area_volume_csv"])
    discharge = load_stage_discharge_curve(base / config["stage_discharge_csv"])
    # Forecast reservoir curves are explicitly synthetic. Scale storage capacity
    # to exercise routing without silently clamping or extrapolating.
    scale = max(1.0, float(inflow["inflow_cms"].max()) / 20 * 8)
    stage_storage = stage_storage.copy()
    stage_storage["storage_m3"] *= scale
    stage_storage["area_m2"] *= scale
    member_input = pd.DataFrame({"datetime": pd.to_datetime(inflow["valid_time"]), "inflow_cms": inflow["inflow_cms"].to_numpy(float)})
    result = route_reservoir_level_pool(member_input, stage_storage, discharge, config)
    metrics = calculate_reservoir_event_metrics(result)
    output = _path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result.to_csv(output / "reservoir_forecast.csv", index=False)
    return {"status": "success", "validation_level": "synthetic_demo", "curve_range_status": "passed_scaled_synthetic_curve", "timeseries": result, "metrics": metrics, "warnings": ["Synthetic scaled storage curve; not for reservoir operation."]}


def run_hec_hms_reservoir_forecast(project_dir: str | Path, rainfall_member: pd.DataFrame, output_dir: str | Path) -> dict[str, Any]:
    return {"status": "blocked_hms_reservoir_gate", "model_id": "hec_hms_reservoir_model", "member_id": str(rainfall_member["member_id"].iloc[0]), "reason": "HEC-HMS Reservoir paired-data/compute gate remains blocked."}


def run_physics_forecast_ensemble(project_dir: str | Path, ensemble: pd.DataFrame, config: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    root = _path(output_dir)
    hydrolite_root = root / "hydrolite_members"
    hms_root = root.parent / "hec_hms_members"
    reservoir_root = root / "reservoir_members"
    timeseries, summaries, reservoir_series, hms_rows = [], [], [], []
    for member_id, member in ensemble.groupby("member_id", sort=False):
        try:
            run = run_hydrolite_forecast_member(project_dir, member, hydrolite_root / f"member_{member_id}")
            timeseries.append(run["timeseries"])
            summaries.append({"model_id": run["model_id"], "member_id": member_id, "run_status": run["status"], "runtime_seconds": run["runtime_seconds"], **run["metrics"], "error_message": ""})
            reservoir_input = run["timeseries"][["valid_time", "reservoir_inflow_cms"]].rename(columns={"reservoir_inflow_cms": "inflow_cms"})
            reservoir = run_hydrolite_reservoir_forecast(reservoir_input, ROOT / "data_demo" / "reservoir" / "demo_reservoir_config.yaml", reservoir_root / f"member_{member_id}")
            routed = reservoir["timeseries"].copy()
            routed["member_id"] = member_id
            routed["valid_time"] = pd.to_datetime(run["timeseries"]["valid_time"].iloc[:len(routed)]).to_numpy()
            reservoir_series.append(routed)
            summaries[-1].update({
                "reservoir_status": reservoir["status"],
                "reservoir_inflow_peak_cms": reservoir["metrics"]["peak_inflow_cms"],
                "reservoir_outflow_peak_cms": reservoir["metrics"]["peak_outflow_cms"],
                "attenuation_percent": reservoir["metrics"]["peak_reduction_percent"],
                "peak_delay_hr": reservoir["metrics"]["peak_time_delay_hours"],
                "maximum_stage_m": reservoir["metrics"]["max_stage_m"],
                "maximum_storage_m3": reservoir["metrics"]["max_storage_m3"],
                "final_storage_m3": reservoir["metrics"]["final_storage_m3"],
                "reservoir_balance_residual_m3": reservoir["metrics"]["residual_m3"],
            })
        except Exception as exc:
            summaries.append({"model_id": "hydrolite_event_model", "member_id": member_id, "run_status": "failed", "runtime_seconds": 0.0, "error_message": str(exc)})
        if len(hms_rows) < min(int(config.get("hec_hms", {}).get("maximum_members", 5)), 5):
            hms_rows.append(run_hec_hms_forecast_member(project_dir, member, hms_root / f"member_{member_id}", execute=bool(config.get("hec_hms", {}).get("enabled", False))))
    return {
        "member_timeseries": pd.concat(timeseries, ignore_index=True) if timeseries else pd.DataFrame(),
        "member_summary": pd.DataFrame(summaries),
        "reservoir_timeseries": pd.concat(reservoir_series, ignore_index=True) if reservoir_series else pd.DataFrame(),
        "hms_summary": pd.DataFrame(hms_rows),
    }


def run_data_driven_forecast_ensemble(project_dir: str | Path, ensemble: pd.DataFrame, config: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    ml = run_ml_synthetic_demo(DEMO_ML, _path(output_dir) / "ml")
    lstm = run_lstm_synthetic_smoke_test(_path(output_dir) / "lstm")
    hybrid = run_hybrid_synthetic_demo(DEMO_ML, _path(output_dir) / "hybrid")
    return {"ml": ml, "lstm": lstm, "hybrid": hybrid}


def combine_forecast_models(results: dict[str, Any], config: dict[str, Any]) -> pd.DataFrame:
    physics = results["physics"]["member_timeseries"].copy()
    reservoir = results["physics"]["reservoir_timeseries"]
    if not reservoir.empty:
        values = reservoir[["member_id", "valid_time", "outflow_cms", "stage_m", "final_storage_m3"]].rename(columns={"outflow_cms": "reservoir_outflow_cms", "stage_m": "reservoir_stage_m", "final_storage_m3": "reservoir_storage_m3"})
        physics = physics.drop(columns=["reservoir_outflow_cms", "reservoir_stage_m", "reservoir_storage_m3"]).merge(values, on=["member_id", "valid_time"], how="left")
    return physics


def calculate_flood_forecast_products(result: pd.DataFrame, thresholds: list[dict[str, Any]] | None = None) -> dict[str, pd.DataFrame]:
    return {
        "ensemble_quantiles": calculate_ensemble_quantiles(result),
        "peak_distribution": calculate_peak_distribution(result),
        "peak_time_distribution": calculate_peak_time_distribution(result),
        "volume_distribution": calculate_volume_distribution(result),
        "reservoir_stage_distribution": calculate_reservoir_stage_distribution(result),
        "threshold_exceedance": calculate_exceedance_probability(result, thresholds or []),
        "uncertainty_sources": classify_uncertainty_sources(None),
    }


def classify_flood_forecast_validation_level(result: dict[str, Any]) -> str:
    return "synthetic_demo"


def summarize_flood_forecast(result: dict[str, Any]) -> dict[str, Any]:
    summary = result["physics"]["member_summary"]
    return {
        "forecast_validation_level": "synthetic_demo",
        "forecast_mode": "hindcast_demo",
        "rainfall_members": int(result["rainfall"]["member_id"].nunique()),
        "hydrolite_success_members": int((summary["run_status"] == "success").sum()),
        "hec_hms_success_members": int((result["physics"]["hms_summary"]["status"] == "success").sum()) if not result["physics"]["hms_summary"].empty else 0,
        "reservoir_success_members": int((summary.get("reservoir_status", pd.Series(dtype=str)) == "success").sum()),
        "ml_members": int(result["data_driven"]["ml"].get("model_count", 0)),
        "lstm_members": 1 if result["data_driven"]["lstm"].get("status") == "passed" else 0,
        "hybrid_members": 1 if result["data_driven"]["hybrid"].get("status") == "passed" else 0,
    }


def _plot_outputs(root: Path, rainfall: pd.DataFrame, ensemble: pd.DataFrame, products: dict[str, pd.DataFrame]) -> None:
    charts = root / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    figures = {}
    fig, ax = plt.subplots()
    for member, group in rainfall.groupby("member_id"):
        ax.plot(pd.to_datetime(group["valid_time"]), group["precipitation_mm"], label=member)
    ax.set_ylabel("mm"); figures["rainfall_ensemble.png"] = fig
    fig, ax = plt.subplots()
    for member, group in ensemble.groupby("member_id"):
        ax.plot(pd.to_datetime(group["valid_time"]), group["outlet_flow_cms"], alpha=.55)
    ax.set_ylabel("m3/s"); figures["outlet_flow_ensemble.png"] = fig
    quantiles = products["ensemble_quantiles"]
    fig, ax = plt.subplots()
    if not quantiles.empty:
        x = pd.to_datetime(quantiles["valid_time"])
        ax.fill_between(x, quantiles["p05"], quantiles["p95"], alpha=.25)
        ax.plot(x, quantiles["p50"])
    figures["outlet_flow_quantiles.png"] = fig
    for name, column in [("reservoir_stage_ensemble.png", "reservoir_stage_m"), ("reservoir_outflow_ensemble.png", "reservoir_outflow_cms")]:
        fig, ax = plt.subplots()
        if column in ensemble:
            for _, group in ensemble.groupby("member_id"):
                ax.plot(pd.to_datetime(group["valid_time"]), group[column], alpha=.55)
        figures[name] = fig
    peaks = ensemble.groupby("member_id")["outlet_flow_cms"].max()
    fig, ax = plt.subplots(); ax.bar(peaks.index, peaks.values); ax.tick_params(axis="x", rotation=45); figures["peak_distribution.png"] = fig
    peak_rows = ensemble.loc[ensemble.groupby("member_id")["outlet_flow_cms"].idxmax()]
    fig, ax = plt.subplots(); ax.bar(peak_rows["member_id"], peak_rows["lead_time_hr"]); ax.tick_params(axis="x", rotation=45); figures["peak_time_distribution.png"] = fig
    volumes = ensemble.assign(volume=ensemble["outlet_flow_cms"] * ensemble["interval_minutes"] * 60).groupby("member_id")["volume"].sum()
    fig, ax = plt.subplots(); ax.bar(volumes.index, volumes.values); ax.tick_params(axis="x", rotation=45); figures["cumulative_volume_ensemble.png"] = fig
    fig, ax = plt.subplots()
    threshold = products["threshold_exceedance"]
    if not threshold.empty:
        ax.bar(threshold["threshold_name"], threshold["scenario_member_exceedance_fraction"])
    figures["threshold_exceedance.png"] = fig
    fig, ax = plt.subplots(); ax.bar(["HydroLite", "HEC-HMS", "ML/LSTM"], [ensemble["member_id"].nunique(), 0, 0]); figures["model_member_comparison.png"] = fig
    for name, figure in figures.items():
        figure.tight_layout()
        figure.savefig(charts / name, dpi=120)
        plt.close(figure)


def write_flood_forecast_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    root = _path(output_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    summary = summarize_flood_forecast(result)
    zh = reports / "flood_forecast_report_zh.md"
    en = reports / "flood_forecast_report_en.md"
    manifest = reports / "flood_forecast_manifest.json"
    zh.write_text(
        "# 洪水预测与多模型集合 MVP\n\n"
        f"- 验证等级：`{summary['forecast_validation_level']}`\n"
        f"- 模式：`{summary['forecast_mode']}`\n"
        f"- HydroLite 成功成员：`{summary['hydrolite_success_members']}`\n"
        "- HEC-HMS Reservoir：`blocked_gate`\n"
        "- 超阈比例是 scenario_member_exceedance_fraction，不是严格概率。\n\n"
        "当前为情景集合与历史回放 MVP。真实业务预测需要实时降雨预报、连续水文状态、多事件独立验证、真实水库曲线和运行监控。\n",
        encoding="utf-8",
    )
    en.write_text(
        "# Flood forecast and multi-model ensemble MVP\n\n"
        f"- Validation level: `{summary['forecast_validation_level']}`\n"
        f"- Mode: `{summary['forecast_mode']}`\n"
        "- Scenario-member fractions are not formal probabilities.\n"
        "- This is not an operational flood-warning system.\n",
        encoding="utf-8",
    )
    manifest.write_text(json.dumps({**summary, "status": "passed_synthetic_demo", "hec_hms_reservoir": "blocked_gate", "operational_forecast": False}, indent=2), encoding="utf-8")
    return {"zh": zh, "en": en, "manifest": manifest}


def export_flood_forecast_bundle(output_dir: str | Path) -> Path:
    root = _path(output_dir)
    bundle = root / "flood_forecast_bundle.zip"
    forbidden = {".dss", ".h5", ".hdf5", ".pt", ".pth", ".ckpt", ".onnx", ".joblib"}
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == bundle or path.suffix.lower() in forbidden or "models" in path.parts:
                continue
            relative = path.relative_to(root)
            if any(part in {"data_raw", "external", "official_reference"} for part in relative.parts):
                continue
            archive.write(path, relative.as_posix())
    return bundle


def validate_flood_forecast_outputs(output_dir: str | Path) -> dict[str, Any]:
    root = _path(output_dir)
    required = [
        "forecast_readiness.json", "forecast_plan.json", "forecast_input_manifest.json",
        "rainfall/rainfall_member_summary.xlsx", "physics/member_run_summary.xlsx",
        "ensemble/ensemble_timeseries.csv", "ensemble/peak_distribution.xlsx",
        "ensemble/reservoir_stage_distribution.xlsx", "reports/flood_forecast_report_zh.md",
        "reports/flood_forecast_report_en.md", "flood_forecast_bundle.zip",
    ]
    missing = [name for name in required if not (root / name).exists()]
    return {"status": "passed" if not missing else "failed", "missing": missing}


def validate_flood_forecast_bundle(output_dir: str | Path) -> dict[str, Any]:
    root = _path(output_dir)
    bundle = root / "flood_forecast_bundle.zip"
    if not bundle.exists():
        return {"status": "failed", "reason": "bundle missing"}
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
    blocked = [name for name in names if name.endswith((".dss", ".h5", ".hdf5", ".pt", ".pth", ".ckpt", ".onnx", ".joblib")) or "data_raw/" in name or "external/" in name]
    return {"status": "passed" if not blocked else "failed", "blocked": blocked, "file_count": len(names)}


def _write_readiness(root: Path, readiness: dict[str, Any]) -> None:
    (root / "forecast_readiness.json").write_text(json.dumps(readiness, indent=2, default=str), encoding="utf-8")
    for language, title in [("zh", "洪水预测就绪度"), ("en", "Flood forecast readiness")]:
        (root / f"forecast_readiness_report_{language}.md").write_text(f"# {title}\n\nStatus: `{readiness['status']}`.\n\nValidation level: `synthetic_demo`.\n", encoding="utf-8")


def run_flood_forecast_project(project_dir: str | Path, config_path: str | Path, output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = _path(output_dir)
    if root.exists():
        shutil.rmtree(root)
    for folder in ("rainfall", "physics", "ml", "lstm", "hybrid", "ensemble", "reports", "charts", "models"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    config = load_flood_forecast_config(config_path)
    check = validate_flood_forecast_config(config)
    if check["status"] != "passed":
        raise ValueError("; ".join(check["errors"]))
    readiness = assess_flood_forecast_readiness(project_dir, config)
    _write_readiness(root, readiness)
    plan = build_flood_forecast_plan(project_dir, config)
    (root / "forecast_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    base = load_forecast_rainfall(ROOT / config.get("rainfall_file", DEMO_RAINFALL))
    baseline = create_observed_replay_scenario(base)
    scaled = create_multiplicative_scenarios(base, [0.8, 1.0, 1.2])
    shifted = create_temporal_shift_scenarios(base, [-1, 1])
    rainfall = pd.concat([baseline, scaled, shifted], ignore_index=True)
    assert rainfall["member_id"].nunique() == 6
    rainfall_paths = write_rainfall_ensemble(root / "rainfall", rainfall)
    write_forecast_input_manifest(root, {"status": "passed", "source": "scenario", "forecast_mode": "hindcast_demo", "rainfall_members": 6, "project_name": _path(project_dir).name})
    physics = run_physics_forecast_ensemble(project_dir, rainfall, config, root / "physics")
    physics["member_timeseries"].to_csv(root / "physics" / "member_forecasts.csv", index=False)
    physics["member_timeseries"].to_csv(root / "physics" / "hydrolite_members.csv", index=False)
    physics["member_summary"].to_excel(root / "physics" / "member_run_summary.xlsx", index=False)
    physics["hms_summary"].to_csv(root / "physics" / "hec_hms_members.csv", index=False)
    physics["reservoir_timeseries"].to_csv(root / "physics" / "reservoir_members.csv", index=False)
    ml_readiness = assess_ml_data_readiness(project_dir)
    (root / "ml" / "ml_readiness.json").write_text(json.dumps(ml_readiness, indent=2), encoding="utf-8")
    (root / "ml" / "ml_readiness_report.md").write_text("# ML readiness\n\nStatus: `insufficient_multi_event_data`. Real RF/GB/LSTM training is blocked; synthetic smoke tests are allowed.\n", encoding="utf-8")
    lstm_readiness = {"status": "insufficient_data", "real_training_ready": False, **detect_torch_environment()}
    (root / "lstm" / "lstm_readiness.json").write_text(json.dumps(lstm_readiness, indent=2, default=str), encoding="utf-8")
    (root / "lstm" / "lstm_readiness_report.md").write_text(
        "# LSTM Readiness\n\n"
        f"- Status: `{lstm_readiness['status']}`\n"
        f"- PyTorch available: `{lstm_readiness['torch_available']}`\n"
        f"- MPS available: `{lstm_readiness['mps_available']}`\n"
        "- Real training ready: `False`\n\n"
        "The repository does not contain sufficient multi-event observations for real LSTM training.\n",
        encoding="utf-8",
    )
    data_driven = run_data_driven_forecast_ensemble(project_dir, rainfall, config, root)
    combined = combine_forecast_models({"physics": physics}, config)
    combined.to_csv(root / "ensemble" / "ensemble_timeseries.csv", index=False)
    thresholds = load_user_flood_thresholds(ROOT / config.get("threshold_file", DEMO_THRESHOLDS))
    products = calculate_flood_forecast_products(combined, thresholds)
    products["ensemble_quantiles"].to_csv(root / "ensemble" / "ensemble_quantiles.csv", index=False)
    for name in ("peak_distribution", "peak_time_distribution", "volume_distribution", "reservoir_stage_distribution", "threshold_exceedance", "uncertainty_sources"):
        products[name].to_excel(root / "ensemble" / f"{name}.xlsx", index=False)
    _plot_outputs(root, rainfall, combined, products)
    write_model_registry_report(root)
    write_capability_registry(root)
    result = {"status": "passed_synthetic_demo", "readiness": readiness, "rainfall": rainfall, "rainfall_paths": rainfall_paths, "physics": physics, "data_driven": data_driven, "ensemble": combined, "products": products}
    write_flood_forecast_report(root, result)
    export_flood_forecast_bundle(root)
    result["validation"] = validate_flood_forecast_outputs(root)
    result["bundle_validation"] = validate_flood_forecast_bundle(root)
    return result


def run_flood_forecast_demo(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    project = DEMO_PROJECT if DEMO_PROJECT.exists() else ROOT
    config = DEMO_CONFIG
    return run_flood_forecast_project(project, config, output_dir)
