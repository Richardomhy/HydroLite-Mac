"""Small, explicit level-pool reservoir routing MVP.

The module intentionally requires a discharge curve.  A stage-storage curve is
evidence for storage only; it never invents an outlet relationship.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _numeric_curve(path: str | Path, columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(_path(path))
    missing = [name for name in columns if name not in frame]
    if missing:
        raise ValueError(f"Curve {path} is missing columns: {', '.join(missing)}")
    return frame.loc[:, columns].apply(pd.to_numeric, errors="coerce").dropna().sort_values(columns[0]).reset_index(drop=True)


def load_stage_area_volume_curve(path: str | Path) -> pd.DataFrame:
    return _numeric_curve(path, ("stage_m", "area_m2", "storage_m3"))


def validate_stage_area_volume_curve(curve: pd.DataFrame) -> dict[str, Any]:
    required = {"stage_m", "area_m2", "storage_m3"}
    if not required.issubset(curve.columns):
        return {"status": "failed", "message": "stage_m, area_m2 and storage_m3 are required."}
    c = curve.sort_values("stage_m")
    errors = []
    if c["stage_m"].duplicated().any() or not c["stage_m"].is_monotonic_increasing: errors.append("stage_m must be strictly increasing")
    if (c["area_m2"] < 0).any(): errors.append("area_m2 must not be negative")
    if c["storage_m3"].duplicated().any() or not c["storage_m3"].is_monotonic_increasing: errors.append("storage_m3 must be strictly increasing")
    return {"status": "passed" if not errors else "failed", "errors": errors, "units": {"stage_m": "m", "area_m2": "m2", "storage_m3": "m3"}, "range": {"stage_m": [float(c.stage_m.min()), float(c.stage_m.max())], "storage_m3": [float(c.storage_m3.min()), float(c.storage_m3.max())]}}


def normalize_stage_storage_units(curve: pd.DataFrame) -> pd.DataFrame:
    """MVP input is already SI; retain explicit units rather than guessing."""
    return curve.copy()


def load_stage_discharge_curve(path: str | Path) -> pd.DataFrame:
    return _numeric_curve(path, ("stage_m", "discharge_cms"))


def validate_stage_discharge_curve(curve: pd.DataFrame) -> dict[str, Any]:
    c = curve.sort_values("stage_m")
    errors = []
    if c.empty or c.stage_m.duplicated().any() or not c.stage_m.is_monotonic_increasing: errors.append("stage_m must be strictly increasing")
    if (c.discharge_cms < 0).any(): errors.append("discharge_cms must not be negative")
    if not c.discharge_cms.is_monotonic_increasing: errors.append("discharge_cms should be monotonic for this MVP")
    return {"status": "passed" if not errors else "failed", "errors": errors, "units": {"stage_m": "m", "discharge_cms": "m3/s"}}


def load_storage_discharge_curve(path: str | Path) -> pd.DataFrame:
    return _numeric_curve(path, ("storage_m3", "discharge_cms"))


def validate_storage_discharge_curve(curve: pd.DataFrame) -> dict[str, Any]:
    renamed = curve.rename(columns={"storage_m3": "stage_m"})
    return validate_stage_discharge_curve(renamed)


def derive_storage_discharge_from_stage_curves(stage_storage: pd.DataFrame, stage_discharge: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"storage_m3": stage_storage.storage_m3, "discharge_cms": np.interp(stage_storage.stage_m, stage_discharge.stage_m, stage_discharge.discharge_cms)})


def interpolate_storage_from_stage(stage: float, curve: pd.DataFrame) -> float:
    return float(np.interp(stage, curve.stage_m, curve.storage_m3))


def interpolate_stage_from_storage(storage: float, curve: pd.DataFrame) -> float:
    return float(np.interp(storage, curve.storage_m3, curve.stage_m))


def interpolate_outflow_from_stage(stage: float, curve: pd.DataFrame) -> float:
    return float(np.interp(stage, curve.stage_m, curve.discharge_cms))


def interpolate_outflow_from_storage(storage: float, curve: pd.DataFrame) -> float:
    return float(np.interp(storage, curve.storage_m3, curve.discharge_cms))


def determine_initial_reservoir_state(config: dict[str, Any], curves: dict[str, pd.DataFrame]) -> dict[str, float]:
    storage_curve = curves["stage_storage"]
    if config.get("initial_storage_m3") is not None:
        storage = float(config["initial_storage_m3"])
        stage = interpolate_stage_from_storage(storage, storage_curve)
    else:
        stage = float(config.get("initial_stage_m", storage_curve.stage_m.iloc[0]))
        storage = interpolate_storage_from_stage(stage, storage_curve)
    return {"initial_stage_m": stage, "initial_storage_m3": storage}


def route_reservoir_level_pool(inflow: pd.DataFrame, stage_storage: pd.DataFrame, discharge_curve: pd.DataFrame | None, config: dict[str, Any]) -> pd.DataFrame:
    if discharge_curve is None:
        raise ValueError("discharge_curve_missing: level-pool routing requires stage-discharge or storage-discharge data.")
    checks = [validate_stage_area_volume_curve(stage_storage), validate_stage_discharge_curve(discharge_curve)]
    if any(check["status"] != "passed" for check in checks):
        raise ValueError(f"curve validation failed: {checks}")
    if "inflow_cms" not in inflow: raise ValueError("inflow_cms is required")
    dt = float(config.get("time_step_hours", 1.0)) * 3600.0
    if dt <= 0: raise ValueError("time_step_hours must be positive")
    state = determine_initial_reservoir_state(config, {"stage_storage": stage_storage})
    min_s, max_s = float(stage_storage.storage_m3.min()), float(stage_storage.storage_m3.max())
    bounded = bool(config.get("allow_boundary_hold", False))
    rows: list[dict[str, Any]] = []
    storage = state["initial_storage_m3"]
    for index, row in inflow.reset_index(drop=True).iterrows():
        qin = float(row.inflow_cms)
        stage0 = interpolate_stage_from_storage(storage, stage_storage)
        qout = interpolate_outflow_from_stage(stage0, discharge_curve)
        provisional = storage + (qin - qout) * dt
        exceedance = provisional < min_s or provisional > max_s
        if exceedance and not bounded:
            raise ValueError(f"curve_range_exceeded at timestep {index}: storage={provisional:.3f} m3; no unconstrained extrapolation is allowed.")
        final_storage = min(max(provisional, min_s), max_s) if bounded else provisional
        stage = interpolate_stage_from_storage(final_storage, stage_storage)
        area = float(np.interp(stage, stage_storage.stage_m, stage_storage.area_m2))
        residual = final_storage - storage - (qin - qout) * dt
        rows.append({"timestep": int(index), "datetime": row.get("datetime", ""), "inflow_cms": qin, "outflow_cms": qout, "initial_storage_m3": storage, "final_storage_m3": final_storage, "storage_change_m3": final_storage-storage, "water_balance_residual_m3": residual, "stage_m": stage, "surface_area_m2": area, "spill_or_exceedance": bool(exceedance)})
        storage = final_storage
    return pd.DataFrame(rows)


def calculate_reservoir_water_balance(result: pd.DataFrame, time_step_hours: float = 1.0) -> dict[str, Any]:
    residual = float(result.water_balance_residual_m3.sum()) if not result.empty else np.nan
    return {"status": "passed" if abs(residual) < 1e-6 else "failed", "residual_m3": residual, "initial_storage_m3": float(result.initial_storage_m3.iloc[0]) if not result.empty else np.nan, "final_storage_m3": float(result.final_storage_m3.iloc[-1]) if not result.empty else np.nan}


def calculate_reservoir_event_metrics(result: pd.DataFrame) -> dict[str, Any]:
    i, o = result.inflow_cms, result.outflow_cms
    peak_i, peak_o = float(i.max()), float(o.max())
    return {"peak_inflow_cms": peak_i, "peak_outflow_cms": peak_o, "peak_reduction_percent": (peak_i-peak_o)/peak_i*100 if peak_i else np.nan, "peak_time_delay_hours": int(o.idxmax()-i.idxmax()), "max_stage_m": float(result.stage_m.max()), "max_storage_m3": float(result.final_storage_m3.max()), "initial_storage_m3": float(result.initial_storage_m3.iloc[0]), "final_storage_m3": float(result.final_storage_m3.iloc[-1]), **calculate_reservoir_water_balance(result)}


def validate_reservoir_routing(result: pd.DataFrame) -> dict[str, Any]:
    required = {"inflow_cms", "outflow_cms", "initial_storage_m3", "final_storage_m3", "stage_m", "water_balance_residual_m3"}
    missing = sorted(required-set(result.columns))
    balance = calculate_reservoir_water_balance(result) if not missing else {"status": "failed"}
    return {"status": "passed" if not missing and balance["status"] == "passed" else "failed", "missing": missing, "water_balance": balance}


def write_reservoir_routing_outputs(output_dir: str | Path, result: pd.DataFrame, metadata: dict[str, Any] | None = None) -> dict[str, Path]:
    root = _path(output_dir); root.mkdir(parents=True, exist_ok=True); charts = root/"charts"; charts.mkdir(exist_ok=True)
    result.to_csv(root/"reservoir_routing_timeseries.csv", index=False)
    metrics = calculate_reservoir_event_metrics(result)
    with pd.ExcelWriter(root/"reservoir_routing_summary.xlsx") as writer:
        pd.DataFrame([metrics]).to_excel(writer, sheet_name="metrics", index=False); result.to_excel(writer, sheet_name="timeseries", index=False)
    fig, ax = plt.subplots(); ax.plot(result.timestep, result.inflow_cms, label="inflow"); ax.plot(result.timestep, result.outflow_cms, label="outflow"); ax.legend(); ax.set_ylabel("m3/s"); fig.tight_layout(); fig.savefig(charts/"inflow_outflow.png", dpi=120); plt.close(fig)
    fig, ax = plt.subplots(); ax.plot(result.timestep, result.stage_m, label="stage"); ax.set_ylabel("m"); fig.tight_layout(); fig.savefig(charts/"stage.png", dpi=120); plt.close(fig)
    report = root/"reservoir_routing_report.md"; report.write_text("# Reservoir routing MVP\n\nLevel-pool routing with an explicit discharge curve. ICESat-2 provides a constraint only; it does not determine outlet releases.\n\n```text\n"+pd.DataFrame([metrics]).to_string(index=False)+"\n```\n", encoding="utf-8")
    manifest = root/"reservoir_routing_manifest.json"; manifest.write_text(json.dumps({"status":"passed", "synthetic_demo":bool((metadata or {}).get("synthetic_demo", False)), "metrics":metrics, "curve_source":(metadata or {}).get("curve_source", "unknown")}, indent=2), encoding="utf-8")
    return {"timeseries":root/"reservoir_routing_timeseries.csv", "summary":root/"reservoir_routing_summary.xlsx", "report":report, "manifest":manifest}


def load_reservoir_config(path: str | Path) -> dict[str, Any]:
    file = _path(path); config = yaml.safe_load(file.read_text(encoding="utf-8")) or {}; config["_config_path"] = str(file); return config


def run_reservoir_demo(config_path: str | Path = ROOT/"data_demo/reservoir/demo_reservoir_config.yaml", output_dir: str | Path = ROOT/"output/reservoir") -> dict[str, Any]:
    config = load_reservoir_config(config_path); base = _path(config_path).parent
    stage_storage = load_stage_area_volume_curve(base/config["stage_area_volume_csv"]); discharge = load_stage_discharge_curve(base/config["stage_discharge_csv"]); inflow = pd.read_csv(base/config["inflow_csv"])
    result = route_reservoir_level_pool(inflow, stage_storage, discharge, config)
    paths = write_reservoir_routing_outputs(output_dir, result, {"synthetic_demo":True,"curve_source":"synthetic_demo_curve"})
    return {"status":"passed", "result":result, "metrics":calculate_reservoir_event_metrics(result), "paths":paths, "curve_checks":{"stage_storage":validate_stage_area_volume_curve(stage_storage),"stage_discharge":validate_stage_discharge_curve(discharge)}}


def reservoir_diagnosis() -> dict[str, Any]:
    return {"status":"available", "method":"level_pool_storage_indication", "limitations":["Discharge curve is mandatory.", "No operational optimization, evaporation, seepage, or unconstrained extrapolation."], "hec_hms":"optional; compute only after open/readiness gates"}


def build_hms_reservoir_project(config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Write an original, reviewable HEC-HMS Reservoir skeleton; never copies samples."""
    cfg = load_reservoir_config(config_path); root = _path(output_dir); root.mkdir(parents=True, exist_ok=True)
    for name in ("data", "scripts", "reports"): (root/name).mkdir(exist_ok=True)
    source = _path(config_path).parent
    for key in ("stage_area_volume_csv", "stage_discharge_csv", "inflow_csv"):
        shutil.copy2(source/cfg[key], root/"data"/Path(cfg[key]).name)
    from hydrolite.hec_hms_format import format_reservoir_outflow_curve
    (root/"data/HydroLite_Outflow_Curve.pdata").write_text(format_reservoir_outflow_curve(load_stage_discharge_curve(source/cfg["stage_discharge_csv"])), encoding="utf-8")
    (root/"HydroLite_Reservoir_Project.hms").write_text("Project: HydroLite Reservoir Project\nVersion: 4.13-compatible skeleton\n", encoding="utf-8")
    (root/"HydroLite_Reservoir_Project.basin").write_text("BasinModel: HydroLite Reservoir Basin\n     Reservoir: DemoReservoir\n          Method: Outflow Curve\n          Initial Elevation: %.3f\n     End:\nEnd:\n" % float(cfg.get("initial_stage_m",100.0)), encoding="utf-8")
    (root/"HydroLite_Reservoir_Project.control").write_text("Control: DemoControl\n     Time Interval: 60\nEnd:\n", encoding="utf-8")
    (root/"HydroLite_Reservoir_Project.run").write_text("Run: DemoRun\n     Basin Model: HydroLite Reservoir Basin\n     Control Specifications: DemoControl\nEnd:\n", encoding="utf-8")
    script=root/"scripts/run_reservoir_probe.sh";script.write_text("#!/bin/sh\necho 'Use: python -m hydrolite reservoir hms-open <project>; compute remains gated until paired data are verified.'\n",encoding="utf-8");script.chmod(0o755)
    manifest = {"status":"project_generation_mvp", "synthetic_demo":True, "runnable_status":"unverified", "warnings":["Original skeleton only; review HEC-HMS Reservoir syntax and paired data in HEC-HMS.", "No official sample was copied."], "files":[str(x) for x in root.rglob('*') if x.is_file()]}
    (root/"reports/hec_hms_reservoir_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    report = root/"reports/hec_hms_reservoir_validation.md"; report.write_text("# HEC-HMS Reservoir project\n\nOriginal Outflow Curve reservoir skeleton. Project generation is not a successful HMS run.\n",encoding="utf-8")
    return {"status":"project_generation_mvp", "project_dir":root, "report":report, "manifest":root/"reports/hec_hms_reservoir_manifest.json"}


def run_hms_reservoir_open_probe(project_dir: str | Path) -> dict[str, Any]:
    from hydrolite.hec_hms import run_hms_open_probe
    result = run_hms_open_probe(project_dir, timeout=60)
    Path(project_dir,"reports/hec_hms_reservoir_open.json").write_text(json.dumps(result,indent=2,default=str),encoding="utf-8"); return result


def run_hms_reservoir_compute_probe(project_dir: str | Path, timeout: int = 120) -> dict[str, Any]:
    from hydrolite.hec_hms import run_hms_compute_probe
    # The original skeleton lacks verified HMS paired-data syntax. Gate it rather than forcing a Java run.
    result = {"status":"skipped_gate_failed", "returncode":None, "runtime_seconds":0.0, "warnings":["Reservoir paired-data syntax is unverified; compute is intentionally not started."], "process_cleanup_confirmed":True}
    Path(project_dir,"reports/hec_hms_reservoir_compute.md").write_text("# HEC-HMS Reservoir compute\n\nStatus: `skipped_gate_failed`; no HMS/Java process was started.\n",encoding="utf-8")
    return result


def extract_hms_reservoir_results(project_dir: str | Path) -> dict[str, Any]:
    root = _path(project_dir); output = root/"reports/hec_hms_reservoir_results.xlsx"
    frame = pd.DataFrame([{"status":"missing", "message":"No verified HEC-HMS Reservoir DSS results were generated; values remain unavailable."}]); frame.to_excel(output,index=False)
    return {"status":"missing", "path":output}


def align_reservoir_timeseries(hydrolite_result: pd.DataFrame, hms_result: pd.DataFrame | None) -> pd.DataFrame:
    if hms_result is None or hms_result.empty: return hydrolite_result.assign(hms_status="missing")
    return hydrolite_result.merge(hms_result, on="timestep", how="left", suffixes=("_hydrolite","_hms"))


def compare_reservoir_routing_metrics(hydrolite_result: pd.DataFrame, hms_result: pd.DataFrame | None) -> dict[str, Any]:
    return {"status":"hms_results_missing" if hms_result is None or hms_result.empty else "compared", "hydrolite_metrics":calculate_reservoir_event_metrics(hydrolite_result), "hms_metrics":None}


def write_reservoir_comparison_report(output_dir: str | Path, hydrolite_result: pd.DataFrame, hms_result: pd.DataFrame | None = None) -> dict[str, Path]:
    root=_path(output_dir);root.mkdir(parents=True,exist_ok=True);charts=root/"charts";charts.mkdir(exist_ok=True);aligned=align_reservoir_timeseries(hydrolite_result,hms_result);aligned.to_csv(root/"aligned_reservoir_timeseries.csv",index=False);metric=compare_reservoir_routing_metrics(hydrolite_result,hms_result)
    with pd.ExcelWriter(root/"reservoir_metrics.xlsx") as writer: pd.DataFrame([metric["hydrolite_metrics"]]).to_excel(writer,index=False,sheet_name="hydrolite")
    report=root/"reservoir_comparison_report_zh.md";report.write_text("# HydroLite/HEC-HMS 水库对比\n\nHEC-HMS Reservoir 结果未验证时，本报告只记录 HydroLite 路由，不虚构跨模型差异。\n",encoding="utf-8");(root/"reservoir_comparison_report_en.md").write_text("# Reservoir comparison\n\nNo HEC-HMS values are invented when results are unavailable.\n",encoding="utf-8")
    bundle=root/"reservoir_comparison_bundle.zip"; 
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        for file in root.glob("*"):
            if file.is_file() and file.suffix.lower() not in {".dss", ".h5", ".hdf5"}: z.write(file,file.name)
    return {"aligned":root/"aligned_reservoir_timeseries.csv","metrics":root/"reservoir_metrics.xlsx","report":report,"bundle":bundle}
