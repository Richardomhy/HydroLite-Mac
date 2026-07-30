"""Bounded single-event calibration and HydroLite--HEC-HMS alignment helpers.

This module deliberately performs a small, deterministic parameter scan.  It is
not an optimizer, a forecast engine, or a substitute for independent observed
flow validation.
"""

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

from hydrolite.config import load_case
from hydrolite.flood_metrics import calculate_event_flow_metrics, compare_event_flow_metrics
from hydrolite.hec_hms_results import align_flow_timeseries, load_hydrolite_outlet_timeseries, run_hms_hydrolite_comparison
from hydrolite.metrics import calculate_all_metrics
from hydrolite.project import list_project_cases, run_project_case
from hydrolite.runner import run_case
from hydrolite.routing import validate_muskingum_parameters
from hydrolite.validate import validate_target


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "calibration"
MAX_CANDIDATES = 40


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _project_case(project_dir: Path) -> Path:
    cases = [path for path in list_project_cases(project_dir) if "aligned" not in path.stem and "calibrated" not in path.stem]
    if not cases:
        raise FileNotFoundError(f"No baseline YAML case found in {project_dir / 'cases'}")
    return cases[0]


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return path


def _safe_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _frame_text(frame: pd.DataFrame) -> str:
    """Avoid making tabulate a runtime dependency just for Markdown tables."""
    return frame.to_csv(index=False) if not frame.empty else "unavailable"


def _interval_hours(frame: pd.DataFrame, column: str) -> float | None:
    values = pd.to_datetime(frame[column], errors="coerce").sort_values().dropna().diff().dt.total_seconds().div(3600)
    return float(values.median()) if not values.empty else None


def discover_calibration_targets(project_dir: str | Path, hms_comparison_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Discover targets in documented priority order without treating HMS as observations."""
    project = _path(project_dir)
    targets: list[dict[str, Any]] = []
    for case_path in list_project_cases(project):
        raw = _read_yaml(case_path)
        observed = raw.get("observed") or {}
        if not observed.get("enabled") or not observed.get("observed_streamflow_csv"):
            continue
        candidate = Path(str(observed["observed_streamflow_csv"])).expanduser()
        if not candidate.is_absolute():
            candidate = (project / candidate).resolve()
        synthetic = "demo" in candidate.name.lower() or bool(observed.get("synthetic_demo", False))
        targets.append(
            {
                "target_mode": "synthetic_demo_calibration" if synthetic else "observed_calibration",
                "target_source": "synthetic_demo_observed" if synthetic else "project_observed_streamflow",
                "target_file": str(candidate),
                "target_element": str(observed.get("gauge_id", "outlet")),
                "time_column": str(observed.get("time_column", "datetime")),
                "flow_column": str(observed.get("flow_column", "observed_streamflow_m3s")),
                "observed_is_synthetic": synthetic,
                "priority": 5 if synthetic else 1,
            }
        )
    comparison = _path(hms_comparison_dir or ROOT / "output" / "hec_hms_comparison")
    hms_csv = comparison / "hec_hms_outlet_timeseries.csv"
    if hms_csv.is_file():
        targets.append(
            {
                "target_mode": "hms_cross_model_alignment",
                "target_source": "HEC-HMS verified outlet series",
                "target_file": str(hms_csv),
                "target_element": "Outlet",
                "time_column": "timestamp",
                "flow_column": "flow_cms",
                "observed_is_synthetic": False,
                "priority": 4,
                "hms_comparison_dir": str(comparison),
            }
        )
    return sorted(targets, key=lambda item: item["priority"])


def select_calibration_target(project_dir: str | Path, target_mode: str = "auto", hms_comparison_dir: str | Path | None = None) -> dict[str, Any]:
    candidates = discover_calibration_targets(project_dir, hms_comparison_dir)
    if target_mode != "auto":
        candidates = [item for item in candidates if item["target_mode"] == target_mode]
    target = dict(candidates[0]) if candidates else {
        "target_mode": "unavailable", "target_source": "unavailable", "target_file": "", "target_element": "",
        "observed_is_synthetic": False, "warnings": ["No observed or HEC-HMS target series was found."],
    }
    target.setdefault("warnings", [])
    target["terminology_to_use"] = {
        "observed_calibration": "model calibration",
        "synthetic_demo_calibration": "synthetic_demo_calibration",
        "hms_cross_model_alignment": "cross-model alignment",
        "unavailable": "unavailable",
    }[target["target_mode"]]
    if target["target_mode"] == "hms_cross_model_alignment":
        target["warnings"].append("HEC-HMS output is a reference model result, not observed streamflow or engineering calibration evidence.")
    if target["target_mode"] == "synthetic_demo_calibration":
        target["warnings"].append("Synthetic/demo observations are only for workflow testing, not real calibration.")
    if target["target_mode"] == "unavailable":
        target["records"] = 0
        return target
    frame = load_calibration_target(target)
    target.update({
        "records": int(len(frame)), "start": str(frame["datetime"].min()), "end": str(frame["datetime"].max()),
        "interval_hours": _interval_hours(frame, "datetime"), "unit": "CMS",
    })
    return target


def load_calibration_target(target_config: dict[str, Any]) -> pd.DataFrame:
    if target_config.get("target_mode") == "unavailable":
        return pd.DataFrame(columns=["datetime", "target_flow_cms"])
    data = pd.read_csv(_path(target_config["target_file"]))
    time_column = target_config.get("time_column", "datetime")
    flow_column = target_config.get("flow_column", "flow_cms")
    missing = [column for column in (time_column, flow_column) if column not in data.columns]
    if missing:
        raise ValueError(f"Calibration target missing required columns: {missing}")
    frame = pd.DataFrame({"datetime": pd.to_datetime(data[time_column], errors="coerce"), "target_flow_cms": pd.to_numeric(data[flow_column], errors="coerce")}).dropna()
    if frame.empty or frame["datetime"].duplicated().any() or not frame["datetime"].is_monotonic_increasing:
        raise ValueError("Calibration target must contain unique increasing timestamps and numeric flow values.")
    return frame


def collect_calibratable_parameters(project_dir: str | Path) -> pd.DataFrame:
    project = _path(project_dir)
    case = load_case(_project_case(project))
    rows: list[dict[str, Any]] = []
    subbasins = pd.read_csv(case.subcatchments_csv)
    reaches = pd.read_csv(case.reaches_csv)
    aliases = {"lag_time_hr": ("lag_time_hr", "hours"), "muskingum_k_hr": ("muskingum_k_hr", "hours"), "muskingum_x": ("muskingum_x", "dimensionless")}
    for _, row in subbasins.iterrows():
        for parameter, unit in (("cn", "dimensionless"), ("initial_abstraction_ratio", "dimensionless"), ("lag_time_hr", "hours")):
            if parameter not in subbasins.columns:
                continue
            value = float(row[parameter])
            rows.append({"element_type": "subbasin", "element_id": str(row["subbasin_id"]), "parameter": parameter, "baseline_value": value, "unit": unit, "source_file": str(case.subcatchments_csv), "source_column": parameter, "stability_constraints": "CN 30-98" if parameter == "cn" else "positive lag" if parameter == "lag_time_hr" else "0-0.50", "warnings": ""})
    for _, row in reaches.iterrows():
        for parameter, (column, unit) in aliases.items():
            if column not in reaches.columns:
                continue
            rows.append({"element_type": "reach", "element_id": str(row["reach_id"]), "parameter": parameter, "baseline_value": float(row[column]), "unit": unit, "source_file": str(case.reaches_csv), "source_column": column, "stability_constraints": "Muskingum stability with dt" if parameter.startswith("muskingum") else "", "warnings": ""})
    return pd.DataFrame(rows)


def build_parameter_bounds(project_dir: str | Path, user_bounds: dict[str, tuple[float, float]] | None = None) -> pd.DataFrame:
    params = collect_calibratable_parameters(project_dir)
    overrides = user_bounds or {}
    rows: list[dict[str, Any]] = []
    for _, item in params.iterrows():
        value = float(item["baseline_value"])
        parameter = str(item["parameter"])
        if parameter == "cn": lower, upper = max(30.0, value - 15.0), min(98.0, value + 15.0)
        elif parameter == "initial_abstraction_ratio": lower, upper = max(0.05, value * 0.5), min(0.30, value * 1.5)
        elif parameter in {"lag_time_hr", "muskingum_k_hr"}: lower, upper = max(0.01, value * 0.5), value * 2.0
        else: lower, upper = max(0.05, value - 0.15), min(0.45, value + 0.15)
        lower, upper = overrides.get(parameter, (lower, upper))
        rows.append({**item.to_dict(), "lower_bound": float(lower), "upper_bound": float(upper)})
    bounds = pd.DataFrame(rows)
    validate_parameter_bounds(bounds)
    return bounds


def validate_parameter_bounds(bounds: pd.DataFrame | dict[str, Any]) -> None:
    frame = pd.DataFrame(bounds) if isinstance(bounds, dict) else bounds
    for _, row in frame.iterrows():
        lower, upper = float(row["lower_bound"]), float(row["upper_bound"])
        parameter = str(row["parameter"])
        if lower > upper:
            raise ValueError(f"Invalid bounds for {parameter}: lower_bound exceeds upper_bound.")
        if parameter == "cn" and not (30 <= lower <= upper <= 98):
            raise ValueError("CN bounds must be within 30-98.")
        if parameter == "initial_abstraction_ratio" and not (0 <= lower <= upper <= 0.50):
            raise ValueError("Initial abstraction ratio bounds must be within 0-0.50.")
        if parameter in {"lag_time_hr", "muskingum_k_hr"} and lower <= 0:
            raise ValueError(f"{parameter} bounds must be positive.")
        if parameter == "muskingum_x" and not (0 <= lower <= upper <= 0.5):
            raise ValueError("Muskingum X bounds must be within 0-0.5.")


def _group_bounds(bounds: pd.DataFrame) -> dict[str, tuple[float, float, float]]:
    result: dict[str, tuple[float, float, float]] = {}
    for parameter, rows in bounds.groupby("parameter"):
        baseline = float(rows["baseline_value"].median())
        if parameter == "cn": result["cn_delta"] = (float(rows["lower_bound"].min()) - baseline, float(rows["upper_bound"].max()) - baseline, 0.0)
        elif parameter in {"lag_time_hr", "muskingum_k_hr"}:
            name = f"{parameter}_multiplier"
            result[name] = (float(rows["lower_bound"].min()) / baseline, float(rows["upper_bound"].max()) / baseline, 1.0)
        else:
            result[parameter] = (float(rows["lower_bound"].min()), float(rows["upper_bound"].max()), baseline)
    return result


def generate_oat_parameter_sets(base_parameters: dict[str, float], bounds: pd.DataFrame, levels: list[float] | None = None) -> list[dict[str, float]]:
    levels = levels or [0.0, 0.25, 0.5, 0.75, 1.0]
    grouped = _group_bounds(bounds)
    baseline = dict(base_parameters or {name: item[2] for name, item in grouped.items()})
    candidates = [baseline]
    for name, (lower, upper, value) in grouped.items():
        for level in levels:
            candidate = dict(baseline)
            candidate[name] = lower + (upper - lower) * level
            candidates.append(candidate)
    return _deduplicate_sets(candidates)


def generate_multivariate_parameter_sets(base_parameters: dict[str, float], bounds: pd.DataFrame, max_candidates: int = 40, seed: int = 42) -> list[dict[str, float]]:
    if max_candidates > MAX_CANDIDATES:
        raise ValueError(f"max_candidates must not exceed {MAX_CANDIDATES}.")
    grouped = _group_bounds(bounds)
    baseline = dict(base_parameters or {name: item[2] for name, item in grouped.items()})
    rng = np.random.default_rng(seed)
    sets = [baseline]
    names = list(grouped)
    for index in range(1, max_candidates):
        candidate: dict[str, float] = {}
        for column, name in enumerate(names):
            lower, upper, _ = grouped[name]
            # Deterministic stratified sample, one dimension permutation per candidate.
            level = ((index - 1 + rng.permutation(max_candidates - 1)[column % (max_candidates - 1)]) % (max_candidates - 1) + rng.random()) / (max_candidates - 1)
            candidate[name] = float(lower + (upper - lower) * level)
        sets.append(candidate)
    return _deduplicate_sets(sets)[:max_candidates]


def _deduplicate_sets(sets: list[dict[str, float]]) -> list[dict[str, float]]:
    seen: set[tuple[tuple[str, float], ...]] = set()
    output: list[dict[str, float]] = []
    for item in sets:
        key = tuple(sorted((name, round(float(value), 10)) for name, value in item.items()))
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _apply_group_parameters(subbasins: pd.DataFrame, reaches: pd.DataFrame, parameters: dict[str, float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    sub = subbasins.copy()
    reach = reaches.copy()
    if "cn_delta" in parameters:
        sub["cn"] = (pd.to_numeric(sub["cn"], errors="coerce") + float(parameters["cn_delta"])).clip(30, 98)
    if "initial_abstraction_ratio" in parameters and "initial_abstraction_ratio" in sub:
        sub["initial_abstraction_ratio"] = float(parameters["initial_abstraction_ratio"])
    if "lag_time_hr_multiplier" in parameters:
        sub["lag_time_hr"] = pd.to_numeric(sub["lag_time_hr"], errors="coerce") * float(parameters["lag_time_hr_multiplier"])
    if "muskingum_k_hr_multiplier" in parameters:
        reach["muskingum_k_hr"] = pd.to_numeric(reach["muskingum_k_hr"], errors="coerce") * float(parameters["muskingum_k_hr_multiplier"])
    if "muskingum_x" in parameters:
        reach["muskingum_x"] = float(parameters["muskingum_x"])
    return sub, reach


def apply_parameter_set_to_workspace(project_dir: str | Path, parameter_set: dict[str, float], workspace_dir: str | Path) -> dict[str, Path]:
    project = _path(project_dir)
    workspace = _path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    baseline = _project_case(project)
    config = load_case(baseline)
    subbasins, reaches = _apply_group_parameters(pd.read_csv(config.subcatchments_csv), pd.read_csv(config.reaches_csv), parameter_set)
    data_dir = workspace / "data"
    data_dir.mkdir(exist_ok=True)
    sub_path, reach_path = data_dir / "subbasins.csv", data_dir / "reaches.csv"
    subbasins.to_csv(sub_path, index=False)
    reaches.to_csv(reach_path, index=False)
    raw = _read_yaml(baseline)
    raw["name"] = f"candidate_{workspace.name.replace('candidate_', '')}"
    raw["inputs"] = {"directory": str(config.rainfall_csv.parent), "rainfall": config.rainfall_csv.name, "subcatchments": str(sub_path), "reaches": str(reach_path)}
    raw["outputs"] = {"directory": str(workspace / "output")}
    raw.pop("observed", None)
    case_path = workspace / "candidate.yaml"
    case_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return {"workspace": workspace, "case": case_path, "subbasins": sub_path, "reaches": reach_path}


def _candidate_stability(reaches: pd.DataFrame, dt_hours: float) -> tuple[bool, str]:
    try:
        for _, row in reaches.iterrows():
            validate_muskingum_parameters(str(row["reach_id"]), float(row["muskingum_k_hr"]), float(row["muskingum_x"]), dt_hours)
    except ValueError as exc:
        return False, str(exc)
    return True, "passed"


def _evaluate(simulated: pd.DataFrame, target: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    simulation = pd.DataFrame({"datetime": pd.to_datetime(simulated["time"], errors="coerce"), "simulated_flow_cms": pd.to_numeric(simulated["outflow_cms"], errors="coerce")})
    aligned = target.merge(simulation, on="datetime", how="inner").dropna()
    metrics = calculate_all_metrics(aligned.get("target_flow_cms", []), aligned.get("simulated_flow_cms", []))
    reference = calculate_event_flow_metrics(aligned.rename(columns={"datetime": "timestamp", "target_flow_cms": "flow_cms"})[["timestamp", "flow_cms"]])
    candidate = calculate_event_flow_metrics(aligned.rename(columns={"datetime": "timestamp", "simulated_flow_cms": "flow_cms"})[["timestamp", "flow_cms"]])
    differences = compare_event_flow_metrics(reference, candidate)
    metrics.update(differences)
    metrics["peak_flow_cms"] = reference.get("peak_flow_cms")
    metrics["runoff_volume_m3"] = reference.get("runoff_volume_m3")
    metrics["records"] = int(len(aligned))
    return metrics, aligned


def calculate_objective_score(metrics: dict[str, Any], objective_config: dict[str, float] | None = None) -> float | None:
    weights = objective_config or {"NSE": .25, "KGE": .20, "PBIAS": .20, "RMSE": .15, "peak_flow_percent_difference": .10, "peak_timing_difference_hr": .05, "runoff_volume_percent_difference": .05}
    peak = max(abs(_safe_float(metrics.get("peak_flow_cms")) or 0), 1.0)
    scores = {
        "NSE": max(0.0, min(1.0, ((_safe_float(metrics.get("NSE")) or -1.0) + 1.0) / 2.0)),
        "KGE": max(0.0, min(1.0, ((_safe_float(metrics.get("KGE")) or -1.0) + 1.0) / 2.0)),
        "PBIAS": max(0.0, 1.0 - min(abs(_safe_float(metrics.get("PBIAS")) or 100.0) / 100.0, 1.0)),
        "RMSE": max(0.0, 1.0 - min((_safe_float(metrics.get("RMSE")) or peak) / peak, 1.0)),
        "peak_flow_percent_difference": max(0.0, 1.0 - min(abs(_safe_float(metrics.get("peak_flow_percent_difference")) or 100.0) / 100.0, 1.0)),
        "peak_timing_difference_hr": max(0.0, 1.0 - min(abs(_safe_float(metrics.get("peak_timing_difference_hr")) or 12.0) / 12.0, 1.0)),
        "runoff_volume_percent_difference": max(0.0, 1.0 - min(abs(_safe_float(metrics.get("runoff_volume_percent_difference")) or 100.0) / 100.0, 1.0)),
    }
    available = {name: weight for name, weight in weights.items() if _safe_float(metrics.get(name)) is not None}
    if not available:
        return None
    return float(sum(scores[name] * weight for name, weight in available.items()) / sum(available.values()))


def evaluate_calibration_candidate(simulated: pd.DataFrame, target: pd.DataFrame, objective_config: dict[str, float] | None = None) -> dict[str, Any]:
    metrics, _ = _evaluate(simulated, target)
    metrics["objective_score"] = calculate_objective_score(metrics, objective_config)
    return metrics


def run_calibration_candidate(project_dir: str | Path, parameter_set: dict[str, float], target: dict[str, Any], workspace_dir: str | Path, timeout: int = 60) -> dict[str, Any]:
    started = time.perf_counter()
    workspace = _path(workspace_dir)
    record: dict[str, Any] = {"workspace": str(workspace), **parameter_set, "run_status": "failed", "rejection_reason": "", "warnings": []}
    try:
        paths = apply_parameter_set_to_workspace(project_dir, parameter_set, workspace)
        config = load_case(paths["case"])
        valid, reason = _candidate_stability(pd.read_csv(paths["reaches"]), config.time_step_hours)
        if not valid:
            record.update({"run_status": "rejected", "rejection_reason": reason, "stability_status": "failed"})
            return record
        record["stability_status"] = "passed"
        # ponytail: small events run synchronously; use a worker process only if candidate timing becomes material.
        outputs = run_case(paths["case"], skip_validate=True)
        if time.perf_counter() - started > timeout:
            record["warnings"].append(f"Candidate exceeded requested {timeout}s guidance after completion.")
        metrics, _ = _evaluate(pd.read_csv(outputs.result_flow_csv), load_calibration_target(target))
        record.update(metrics)
        record["objective_score"] = calculate_objective_score(metrics)
        score_name = "alignment_score" if target.get("target_mode") == "hms_cross_model_alignment" else "observed_calibration_score"
        record[score_name] = record["objective_score"]
        record["run_status"] = "success" if record["objective_score"] is not None else "failed"
        record["result_flow_csv"] = str(outputs.result_flow_csv)
    except Exception as exc:  # noqa: BLE001
        record["rejection_reason"] = str(exc)
    finally:
        record["runtime_seconds"] = round(time.perf_counter() - started, 4)
        record["warnings"] = "; ".join(record["warnings"])
    return record


def _plot_frame(frame: pd.DataFrame, path: Path, x: str, y: str, title: str, kind: str = "scatter") -> Path | None:
    clean = frame.copy()
    if x not in clean or y not in clean:
        return None
    clean[x], clean[y] = pd.to_numeric(clean[x], errors="coerce"), pd.to_numeric(clean[y], errors="coerce")
    clean = clean.dropna(subset=[x, y])
    if clean.empty:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if kind == "bar": ax.bar(clean[x].astype(str), clean[y])
    else: ax.scatter(clean[x], clean[y])
    ax.set(title=title, xlabel=x, ylabel=y)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)
    return path


def run_oat_sensitivity(project_dir: str | Path, target: dict[str, Any], bounds: pd.DataFrame, output_dir: str | Path, levels: list[float] | None = None) -> dict[str, Any]:
    output = _path(output_dir); output.mkdir(parents=True, exist_ok=True)
    grouped = _group_bounds(bounds); baseline = {name: values[2] for name, values in grouped.items()}
    sets = generate_oat_parameter_sets(baseline, bounds, levels)
    rows = []
    for index, parameter_set in enumerate(sets):
        result = run_calibration_candidate(project_dir, parameter_set, target, output / "workspaces" / f"candidate_{index:03d}")
        result["candidate_id"] = f"oat_{index:03d}"; result["candidate_kind"] = "baseline" if index == 0 else "oat"; rows.append(result)
    results = pd.DataFrame(rows)
    candidates = pd.DataFrame([{ "candidate_id": f"oat_{idx:03d}", **item} for idx, item in enumerate(sets)])
    candidates.to_excel(output / "oat_candidates.xlsx", index=False)
    results.to_excel(output / "oat_results.xlsx", index=False)
    sensitivity = calculate_parameter_sensitivity(results)
    sensitivity.to_excel(output / "parameter_sensitivity.xlsx", index=False); sensitivity.to_csv(output / "parameter_sensitivity.csv", index=False)
    charts = plot_parameter_sensitivity(sensitivity, output)
    report = write_sensitivity_report(output, {"results": results, "sensitivity": sensitivity, "charts": charts, "group_parameter_adjustment": True})
    return {"results": results, "sensitivity": sensitivity, "candidates": candidates, "report": report, "charts": charts}


def calculate_parameter_sensitivity(oat_results: pd.DataFrame) -> pd.DataFrame:
    parameter_columns = [name for name in ("cn_delta", "initial_abstraction_ratio", "lag_time_hr_multiplier", "muskingum_k_hr_multiplier", "muskingum_x") if name in oat_results]
    baseline = oat_results[oat_results.get("candidate_kind", "").eq("baseline")].head(1)
    rows: list[dict[str, Any]] = []
    for parameter in parameter_columns:
        varied = oat_results[oat_results[parameter].notna() & oat_results["run_status"].eq("success")]
        if varied.empty:
            continue
        baseline_score = _safe_float(baseline.iloc[0].get("objective_score")) if not baseline.empty else None
        values = pd.to_numeric(varied[parameter], errors="coerce")
        scores = pd.to_numeric(varied.get("objective_score"), errors="coerce")
        correlation = values.corr(scores) if values.notna().sum() >= 2 and scores.notna().sum() >= 2 and values.std() > 0 and scores.std() > 0 else np.nan
        effect = float(scores.max() - scores.min()) if scores.notna().any() else np.nan
        rows.append({"parameter_group": parameter, "objective_score_range": effect, "objective_correlation": correlation, "baseline_objective_score": baseline_score, "peak_flow_range": pd.to_numeric(varied.get("peak_flow_cms"), errors="coerce").max() - pd.to_numeric(varied.get("peak_flow_cms"), errors="coerce").min(), "volume_range": pd.to_numeric(varied.get("runoff_volume_m3"), errors="coerce").max() - pd.to_numeric(varied.get("runoff_volume_m3"), errors="coerce").min(), "nse_range": pd.to_numeric(varied.get("NSE"), errors="coerce").max() - pd.to_numeric(varied.get("NSE"), errors="coerce").min(), "kge_range": pd.to_numeric(varied.get("KGE"), errors="coerce").max() - pd.to_numeric(varied.get("KGE"), errors="coerce").min(), "failure_rate": float((oat_results["run_status"] != "success").mean()), "nonlinear_diagnostic": "range-based single-event diagnostic"})
    return pd.DataFrame(rows).sort_values("objective_score_range", ascending=False, na_position="last") if rows else pd.DataFrame()


def rank_parameter_sensitivity(sensitivity: pd.DataFrame) -> pd.DataFrame:
    return sensitivity.sort_values("objective_score_range", ascending=False, na_position="last").reset_index(drop=True)


def plot_parameter_sensitivity(sensitivity: pd.DataFrame, output_dir: str | Path) -> dict[str, Path]:
    output = _path(output_dir) / "charts"; output.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    for field, filename in (("peak_flow_range", "parameter_vs_peak_flow.png"), ("volume_range", "parameter_vs_volume.png"), ("nse_range", "parameter_vs_nse.png"), ("kge_range", "parameter_vs_kge.png"), ("objective_score_range", "parameter_sensitivity_ranking.png")):
        chart = _plot_frame(sensitivity, output / filename, "parameter_group", field, field, "bar")
        if chart: outputs[field] = chart
    return outputs


def write_sensitivity_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    output = _path(output_dir); path = output / "sensitivity_report.md"; frame = result["sensitivity"]
    path.write_text("# HydroLite Parameter Sensitivity Report\n\n- group_parameter_adjustment: `true`\n- This is a bounded single-event diagnostic, not forecast calibration.\n\n" + _frame_text(frame) + "\n", encoding="utf-8")
    return path


def run_parameter_search(project_dir: str | Path, target: dict[str, Any], bounds: pd.DataFrame, output_dir: str | Path, max_candidates: int = 30, seed: int = 42) -> dict[str, Any]:
    if max_candidates > MAX_CANDIDATES: raise ValueError(f"max_candidates must not exceed {MAX_CANDIDATES}.")
    output = _path(output_dir); output.mkdir(parents=True, exist_ok=True)
    grouped = _group_bounds(bounds); sets = generate_multivariate_parameter_sets({name: values[2] for name, values in grouped.items()}, bounds, max_candidates, seed)
    rows = []
    for index, parameter_set in enumerate(sets):
        result = run_calibration_candidate(project_dir, parameter_set, target, output / "workspaces" / f"candidate_{index:03d}")
        result.update({"candidate_id": f"candidate_{index:03d}", "candidate_kind": "baseline" if index == 0 else "search"}); rows.append(result)
    candidates = pd.DataFrame(rows)
    ranked = rank_calibration_candidates(candidates)
    candidates.to_excel(output / "calibration_candidates.xlsx", index=False); candidates.to_csv(output / "calibration_candidates.csv", index=False); ranked.to_excel(output / "candidate_ranking.xlsx", index=False)
    rejected = candidates[candidates["run_status"] != "success"]; rejected.to_excel(output / "rejected_candidates.xlsx", index=False)
    best = select_best_calibration_candidate(candidates)
    (output / "best_candidate.yaml").write_text(yaml.safe_dump(best or {}, sort_keys=False), encoding="utf-8")
    (output / "top_candidates.yaml").write_text(yaml.safe_dump(ranked.head(5).to_dict(orient="records"), sort_keys=False), encoding="utf-8")
    charts = _write_search_charts(candidates, output / "charts")
    report = write_parameter_search_report(output, {"results": candidates, "ranked": ranked, "best": best, "target": target, "charts": charts})
    return {"results": candidates, "ranked": ranked, "best": best, "report": report, "charts": charts}


def generate_deterministic_sample(bounds: pd.DataFrame, max_candidates: int, seed: int = 42) -> list[dict[str, float]]:
    return generate_multivariate_parameter_sets({}, bounds, max_candidates, seed)


def rank_calibration_candidates(results: pd.DataFrame) -> pd.DataFrame:
    return results[results["run_status"].eq("success")].sort_values("objective_score", ascending=False, na_position="last").reset_index(drop=True)


def validate_candidate_result(result: dict[str, Any]) -> bool:
    return result.get("run_status") == "success" and result.get("stability_status") == "passed" and _safe_float(result.get("objective_score")) is not None


def select_best_calibration_candidate(results: pd.DataFrame) -> dict[str, Any] | None:
    ranked = rank_calibration_candidates(results)
    if ranked.empty: return None
    item = ranked.iloc[0].to_dict()
    return {key: (value.item() if isinstance(value, np.generic) else value) for key, value in item.items() if key not in {"warnings"}}


def _write_search_charts(frame: pd.DataFrame, output: Path) -> dict[str, Path]:
    output.mkdir(parents=True, exist_ok=True); success = frame[frame["run_status"].eq("success")]
    charts: dict[str, Path] = {}
    for x, y, name in (("candidate_id", "objective_score", "candidate_objective_scores.png"), ("NSE", "KGE", "nse_kge_scatter.png"), ("PBIAS", "RMSE", "pbias_rmse_scatter.png"), ("peak_flow_percent_difference", "runoff_volume_percent_difference", "peak_volume_error.png")):
        chart = _plot_frame(success, output / name, x, y, name, "bar" if x == "candidate_id" else "scatter")
        if chart: charts[name] = chart
    return charts


def write_parameter_search_report(output_dir: str | Path, result: dict[str, Any]) -> Path:
    path = _path(output_dir) / "parameter_search_report.md"; best = result.get("best") or {}
    path.write_text("# HydroLite Parameter Search Report\n\n" + f"- target mode: `{result['target'].get('target_mode')}`\n- candidates attempted: `{len(result['results'])}`\n- candidates succeeded: `{len(result['ranked'])}`\n- best candidate: `{best.get('candidate_id', 'unavailable')}`\n- best score: `{best.get('objective_score', 'unavailable')}`\n- This is bounded single-event {result['target'].get('terminology_to_use')}; it does not establish independent validation.\n", encoding="utf-8")
    return path


def create_calibrated_case(project_dir: str | Path, best_candidate: dict[str, Any] | None, output_case: str | Path) -> dict[str, Path]:
    if not best_candidate: raise ValueError("No successful best candidate is available.")
    project = _path(project_dir); baseline = _project_case(project); config = load_case(baseline)
    generated = project / "data" / "generated" / "calibration"; generated.mkdir(parents=True, exist_ok=True)
    sub, reach = _apply_group_parameters(pd.read_csv(config.subcatchments_csv), pd.read_csv(config.reaches_csv), {key: float(best_candidate[key]) for key in _group_bounds(build_parameter_bounds(project)) if key in best_candidate})
    sub_path, reach_path = generated / "subbasins_aligned.csv", generated / "reaches_aligned.csv"; sub.to_csv(sub_path, index=False); reach.to_csv(reach_path, index=False)
    parameters_path = generated / "best_parameters.yaml"; parameters_path.write_text(yaml.safe_dump({key: best_candidate[key] for key in _group_bounds(build_parameter_bounds(project)) if key in best_candidate}, sort_keys=False), encoding="utf-8")
    raw = _read_yaml(baseline); target_name = "qgis_demo_aligned" if "qgis_demo" in baseline.stem else f"{baseline.stem}_aligned"; raw["name"] = target_name; raw["inputs"] = {"directory": str(config.rainfall_csv.parent), "rainfall": config.rainfall_csv.name, "subcatchments": str(sub_path), "reaches": str(reach_path)}; raw["outputs"] = {"directory": f"output/{target_name}"}; raw.pop("observed", None)
    case_path = _path(output_case); case_path.parent.mkdir(parents=True, exist_ok=True); case_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    manifest = generated / "calibration_manifest.json"; _write_json(manifest, {"target_mode": best_candidate.get("target_mode", "hms_cross_model_alignment"), "baseline_case": str(baseline), "generated_case": str(case_path), "best_candidate": best_candidate.get("candidate_id"), "parameter_changes": {key: best_candidate[key] for key in _group_bounds(build_parameter_bounds(project)) if key in best_candidate}, "validation_status": "unavailable_single_event", "limitations": ["Single event only; no independent event validation."], "generated_at": _now()})
    return {"case": case_path, "subbasins": sub_path, "reaches": reach_path, "parameters": parameters_path, "manifest": manifest}


def validate_calibrated_case(case_path: str | Path) -> Any:
    return validate_target(case_path)


def run_calibrated_case(case_path: str | Path) -> Any:
    return run_case(case_path)


def _comparison_metric_row(path: Path) -> dict[str, Any]:
    data = pd.read_excel(path, sheet_name="comparison_metrics")
    return data.iloc[0].to_dict() if not data.empty else {}


def compare_best_case(project_dir: str | Path, hms_project_dir: str | Path, output_dir: str | Path = ROOT / "output" / "hec_hms_alignment_best") -> dict[str, Any]:
    project = _path(project_dir); case = project / "cases" / "qgis_demo_aligned.yaml"; outputs = run_project_case(project, case.name)
    comparison = run_hms_hydrolite_comparison(hms_project_dir, project, output_dir=output_dir, hydrolite_result_csv=outputs.result_flow_csv)
    output = _path(output_dir); baseline_metrics = _comparison_metric_row(ROOT / "output" / "hec_hms_comparison" / "model_comparison_metrics.xlsx")
    best_metrics = comparison.get("comparison_metrics", {})
    with pd.ExcelWriter(output / "baseline_vs_best_metrics.xlsx") as writer:
        pd.DataFrame([{"model": "baseline", **baseline_metrics}, {"model": "best", **best_metrics}]).to_excel(writer, index=False)
    pd.DataFrame([best_metrics]).to_excel(output / "best_alignment_metrics.xlsx", index=False)
    charts = output / "charts"; charts.mkdir(exist_ok=True)
    baseline_flow = ROOT / "output" / "hec_hms_comparison" / "aligned_outlet_timeseries.csv"
    best_flow = output / "aligned_outlet_timeseries.csv"
    if baseline_flow.exists() and best_flow.exists():
        baseline_frame, best_frame = pd.read_csv(baseline_flow), pd.read_csv(best_flow)
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for frame, label, column in ((baseline_frame, "HydroLite baseline", "hydrolite_flow_cms"), (best_frame, "HydroLite aligned", "hydrolite_flow_cms")):
            if {"timestamp", column} <= set(frame.columns):
                ax.plot(pd.to_datetime(frame["timestamp"]), frame[column], label=label)
        if {"timestamp", "hms_flow_cms"} <= set(best_frame.columns):
            ax.plot(pd.to_datetime(best_frame["timestamp"]), best_frame["hms_flow_cms"], label="HEC-HMS reference", linestyle="--")
        ax.set(title="Baseline vs aligned HydroLite outlet flow", xlabel="time", ylabel="flow (cms)"); ax.legend(); fig.autofmt_xdate(); fig.tight_layout()
        fig.savefig(charts / "baseline_vs_best_hydrograph.png", dpi=150); plt.close(fig)
    ranking = ROOT / "output" / "calibration" / "search" / "candidate_ranking.xlsx"
    if ranking.exists():
        ranked = pd.read_excel(ranking).head(5)
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for _, row in ranked.iterrows():
            candidate_flow = Path(str(row.get("result_flow_csv", "")))
            if candidate_flow.exists():
                frame = pd.read_csv(candidate_flow)
                ax.plot(pd.to_datetime(frame["time"]), frame["outflow_cms"], label=str(row.get("candidate_id")))
        if ax.lines:
            ax.set(title="Top candidate outlet hydrographs", xlabel="time", ylabel="flow (cms)"); ax.legend(); fig.autofmt_xdate(); fig.tight_layout()
            fig.savefig(charts / "top_candidates_hydrographs.png", dpi=150)
        plt.close(fig)
    report = output / "best_alignment_report.md"; report.write_text("# HydroLite-HEC-HMS Cross-model Alignment Report\n\n## Chinese title\n\nHydroLite-HEC-HMS 跨模型对齐报告\n\n- Target is HEC-HMS model output, not observed flow.\n- Validation status: `unavailable_single_event`.\n\n" + _frame_text(pd.DataFrame([{"baseline": baseline_metrics, "best": best_metrics}])) + "\n", encoding="utf-8")
    comparison_frame = pd.DataFrame([{"scenario": "baseline", **baseline_metrics}, {"scenario": "aligned", **best_metrics}])
    report.write_text(
        "# HydroLite-HEC-HMS Cross-model Alignment Report\n\n"
        "# HydroLite-HEC-HMS 跨模型对齐报告\n\n"
        "- Target: HEC-HMS verified Outlet flow; it is a model reference, not observed streamflow.\n"
        "- Event: one exact-timestamp matched event.\n"
        "- Objective: weighted NSE, KGE, PBIAS, RMSE, peak, timing and volume diagnostics.\n"
        "- Validation status: unavailable_single_event; no independent-event validation is claimed.\n"
        "- Interpretation: a limited cross-model consistency check, not a forecast or engineering-design conclusion.\n\n"
        "## Baseline and aligned comparison\n\n" + _frame_text(comparison_frame) + "\n",
        encoding="utf-8",
    )
    _write_json(output / "alignment_manifest.json", {"target_mode": "hms_cross_model_alignment", "baseline_metrics": baseline_metrics, "best_metrics": best_metrics, "validation_status": "unavailable_single_event", "generated_at": _now()})
    return {"outputs": outputs, "comparison": comparison, "report": report, "output_dir": output}


def classify_calibration_quality(metrics: dict[str, Any], target_mode: str, validation_status: str) -> str:
    if validation_status == "unavailable_single_event":
        return "insufficient_data" if _safe_float(metrics.get("objective_score")) is None else "limited_improvement"
    score = _safe_float(metrics.get("objective_score"))
    if score is None: return "insufficient_data"
    return "substantial_improvement" if score >= .75 else "moderate_improvement" if score >= .55 else "limited_improvement" if score >= .35 else "no_improvement"


def write_calibration_quality_statement(output_dir: str | Path, result: dict[str, Any]) -> Path:
    path = _path(output_dir) / "calibration_quality_statement.md"; quality = classify_calibration_quality(result.get("best", {}), result.get("target", {}).get("target_mode", "unavailable"), "unavailable_single_event")
    path.write_text(f"# Calibration / Alignment Quality Statement\n\n- classification: `{quality}`\n- single-event results do not provide independent validation.\n", encoding="utf-8")
    return path


def write_calibration_report(output_dir: str | Path, result: dict[str, Any] | None = None) -> Path:
    output = _path(output_dir); target_file = output / "calibration_target.json"; target = json.loads(target_file.read_text()) if target_file.exists() else {}
    path = output / "calibration_report.md"
    candidates_file = output / "search" / "calibration_candidates.xlsx"
    candidates = pd.read_excel(candidates_file) if candidates_file.exists() else pd.DataFrame()
    baseline = candidates[candidates.get("candidate_kind", "").eq("baseline")].head(1)
    best = candidates[candidates.get("run_status", "").eq("success")].sort_values("objective_score", ascending=False).head(1) if not candidates.empty else pd.DataFrame()
    selected = pd.concat([baseline.assign(scenario="baseline"), best.assign(scenario="best")], ignore_index=True)
    columns = [column for column in ("scenario", "candidate_id", "objective_score", "alignment_score", "observed_calibration_score", "NSE", "KGE", "RMSE", "PBIAS", "peak_flow_percent_difference", "peak_timing_difference_hr", "runoff_volume_percent_difference", "cn_delta", "initial_abstraction_ratio", "lag_time_hr_multiplier", "muskingum_k_hr_multiplier", "muskingum_x") if column in selected]
    path.write_text(
        "# HydroLite Calibration / Alignment Report\n\n"
        f"- terminology: {target.get('terminology_to_use', 'unavailable')}\n"
        f"- target mode: {target.get('target_mode', 'unavailable')}\n"
        f"- target source: {target.get('target_source', 'unavailable')}\n"
        "- validation status: unavailable_single_event\n"
        "- HEC-HMS output is never treated as observed flow.\n"
        "- Candidate parameters are constrained and each Muskingum candidate is checked before it runs.\n"
        "- Do not infer forecast skill, independent validation, or engineering design suitability from this single event.\n\n"
        "## Baseline and best candidate\n\n" + _frame_text(selected[columns]) + "\n",
        encoding="utf-8",
    )
    return path


def export_calibration_bundle(output_dir: str | Path) -> Path:
    output = _path(output_dir); bundle = output / "calibration_bundle.zip"; forbidden = ("data_raw", "external", ".dss", "secret", "credential", ".pt", ".pth", ".ckpt", ".onnx")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if not path.is_file() or path == bundle: continue
            relative = path.relative_to(output).as_posix().lower()
            if any(token in relative for token in forbidden) or "/workspaces/" in f"/{relative}": continue
            archive.write(path, path.relative_to(output).as_posix())
    return bundle


def write_target_outputs(project_dir: str | Path, hms_comparison_dir: str | Path | None = None, output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output = _path(output_dir); target = select_calibration_target(project_dir, hms_comparison_dir=hms_comparison_dir)
    _write_json(output / "calibration_target.json", target)
    (output / "calibration_target_report.md").write_text("# Calibration Target Diagnostic\n\n" + "\n".join(f"- {key}: `{value}`" for key, value in target.items() if key != "warnings") + "\n\n" + "\n".join(f"- WARNING: {warning}" for warning in target.get("warnings", [])) + "\n", encoding="utf-8")
    (output / "calibration_validation_plan.json").write_text(json.dumps({"validation_status": "unavailable_single_event", "message": "One event cannot establish independent validation."}, indent=2) + "\n", encoding="utf-8")
    (output / "calibration_validation_plan.md").write_text("# Calibration Validation Plan\n\nvalidation_status = `unavailable_single_event`\n\nDo not call a within-event split independent validation.\n", encoding="utf-8")
    return target


def write_parameter_outputs(project_dir: str | Path, output_dir: str | Path = DEFAULT_OUTPUT) -> tuple[pd.DataFrame, pd.DataFrame]:
    output = _path(output_dir); output.mkdir(parents=True, exist_ok=True)
    parameters, bounds = collect_calibratable_parameters(project_dir), build_parameter_bounds(project_dir)
    parameters.to_excel(output / "baseline_parameters.xlsx", index=False); _write_json(output / "baseline_parameters.json", parameters.to_dict(orient="records")); bounds.to_excel(output / "parameter_bounds.xlsx", index=False)
    (output / "parameter_bounds.md").write_text("# Parameter Bounds\n\n" + _frame_text(bounds) + "\n", encoding="utf-8")
    return parameters, bounds


def create_multi_event_calibration_objective(events: Any, weights: str | dict[str, float] = "equal") -> dict[str, Any]:
    ids = events["event_id"].astype(str).tolist() if isinstance(events, pd.DataFrame) else [str(item["event_id"] if isinstance(item, dict) else item) for item in events]
    values = {event_id: float(weights.get(event_id, 0)) for event_id in ids} if isinstance(weights, dict) else {event_id: 1.0 for event_id in ids}
    total = sum(values.values()) or 1.0
    return {"event_weights": {key: value / total for key, value in values.items()}, "weighting": weights if isinstance(weights, str) else "user_defined", "metrics": ["NSE", "KGE", "PBIAS"], "single_event_dominance_guard": True}


def evaluate_parameter_set_across_events(parameters: dict[str, float], events: Any, project_dir: str | Path | None = None) -> dict[str, Any]:
    from hydrolite.event_dataset import build_event_dataset
    from hydrolite.hindcast import DEFAULT_OUTPUT as HINDCAST_OUTPUT, _source_for_project, run_hydrolite_hindcast_event
    project = Path(project_dir or Path(__file__).resolve().parents[1] / "projects" / "qgis_workflow_project")
    source = _source_for_project(project)
    rows = []
    records = events.to_dict("records") if isinstance(events, pd.DataFrame) else list(events)
    for event in records:
        dataset = build_event_dataset(event, source)
        rows.append(run_hydrolite_hindcast_event(project, dataset, parameters, HINDCAST_OUTPUT / "calibration" / "_scratch", write_outputs=False))
    frame = pd.DataFrame(rows)
    success = frame[frame.get("run_status", pd.Series(dtype=str)).eq("success")]
    return {
        "parameters": dict(parameters), "events": frame, "success_count": len(success),
        "median_NSE": float(pd.to_numeric(success.get("NSE"), errors="coerce").median()) if len(success) else np.nan,
        "median_KGE": float(pd.to_numeric(success.get("KGE"), errors="coerce").median()) if len(success) else np.nan,
        "median_abs_PBIAS": float(pd.to_numeric(success.get("PBIAS"), errors="coerce").abs().median()) if len(success) else np.nan,
        "worst_NSE": float(pd.to_numeric(success.get("NSE"), errors="coerce").min()) if len(success) else np.nan,
    }


def rank_parameter_sets_multi_event(results: pd.DataFrame) -> pd.DataFrame:
    frame = results.copy()
    frame["robust_score"] = (
        pd.to_numeric(frame["median_NSE"], errors="coerce").fillna(-1) * .35
        + pd.to_numeric(frame["median_KGE"], errors="coerce").fillna(-1) * .30
        + pd.to_numeric(frame["worst_NSE"], errors="coerce").fillna(-1) * .20
        + (1 - pd.to_numeric(frame["median_abs_PBIAS"], errors="coerce").fillna(100).clip(0, 100) / 100) * .15
    )
    return frame.sort_values(["robust_score", "worst_NSE"], ascending=False).reset_index(drop=True)


def detect_event_specific_overfitting(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty or not {"median_NSE", "worst_NSE"}.issubset(results):
        return {"status": "insufficient_data", "detected": False}
    best = results.sort_values("median_NSE", ascending=False).iloc[0]
    gap = float(best["median_NSE"] - best["worst_NSE"])
    return {"status": "warning" if gap > .5 else "passed", "detected": gap > .5, "median_worst_gap": gap}


def calculate_parameter_stability(results: pd.DataFrame) -> dict[str, Any]:
    ranked = rank_parameter_sets_multi_event(results)
    top = ranked.head(min(5, len(ranked)))
    limits = {"cn_delta": 8, "lag_multiplier": .5, "k_multiplier": .5, "x_delta": .1}
    rows = []
    for name, limit in limits.items():
        if name not in top:
            continue
        values = pd.to_numeric(top[name], errors="coerce")
        rows.append({"parameter": name, "mean": values.mean(), "std": values.std(ddof=0), "range": values.max() - values.min(), "stability_limit": limit})
    frame = pd.DataFrame(rows)
    stable = bool(len(frame) and (frame["range"].fillna(0) <= frame["stability_limit"]).all())
    return {"status": "stable" if stable else "variable", "parameters": frame}


def select_robust_parameter_set(results: pd.DataFrame) -> dict[str, Any]:
    ranked = rank_parameter_sets_multi_event(results)
    if ranked.empty:
        return {}
    row = ranked.iloc[0]
    return {name: float(row[name]) for name in ("cn_delta", "lag_multiplier", "k_multiplier", "x_delta") if name in row}


def validate_robust_parameter_set(parameters: dict[str, float], validation_events: Any, project_dir: str | Path | None = None) -> dict[str, Any]:
    result = evaluate_parameter_set_across_events(parameters, validation_events, project_dir)
    return {**result, "status": "passed" if result["success_count"] == len(validation_events) else "failed", "events_used_for_fitting": False}


def run_multi_event_parameter_search(project_dir: str | Path, calibration_events: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    from hydrolite.hindcast import DEFAULT_OUTPUT as HINDCAST_OUTPUT
    settings = config or {}
    maximum = int(settings.get("max_candidates", 30))
    if not 1 <= maximum <= 60:
        raise ValueError("multi-event calibration candidates must be in [1, 60]")
    rng = np.random.default_rng(int(settings.get("random_seed", 42)))
    candidates = [{"cn_delta": 0.0, "lag_multiplier": 1.0, "k_multiplier": 1.0, "x_delta": 0.0}]
    for _ in range(maximum - 1):
        candidates.append({
            "cn_delta": float(rng.uniform(-6, 6)), "lag_multiplier": float(rng.uniform(.75, 1.35)),
            "k_multiplier": float(rng.uniform(.75, 1.35)), "x_delta": float(rng.uniform(-.08, .08)),
        })
    rows = []
    for index, parameters in enumerate(candidates):
        evaluation = evaluate_parameter_set_across_events(parameters, calibration_events, project_dir)
        rows.append({"candidate_id": f"multi_{index:03d}", **parameters, **{key: evaluation[key] for key in ("success_count", "median_NSE", "median_KGE", "median_abs_PBIAS", "worst_NSE")}})
    frame = pd.DataFrame(rows)
    result = {
        "candidates": frame, "ranked": rank_parameter_sets_multi_event(frame),
        "best": select_robust_parameter_set(frame), "stability": calculate_parameter_stability(frame),
        "overfitting": detect_event_specific_overfitting(frame),
    }
    write_multi_event_calibration_report(settings.get("output_dir", HINDCAST_OUTPUT / "calibration"), result)
    return result


def write_multi_event_calibration_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    candidates, ranked = result["candidates"], result["ranked"]
    candidates.to_excel(output / "candidates.xlsx", index=False)
    ranked.to_excel(output / "multi_event_objectives.xlsx", index=False)
    result["stability"]["parameters"].to_excel(output / "parameter_stability.xlsx", index=False)
    (output / "robust_parameters.yaml").write_text(yaml.safe_dump(result["best"], sort_keys=False), encoding="utf-8")
    paths = {}
    for language, title in (("zh", "HydroLite 多事件率定报告"), ("en", "HydroLite Multi-event Calibration Report")):
        path = output / f"calibration_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Candidates: `{len(candidates)}`\n- Successful: `{int((candidates['success_count'] > 0).sum())}`\n"
            f"- Robust parameters: `{result['best']}`\n- Stability: `{result['stability']['status']}`\n"
            f"- Event-specific overfitting detected: `{result['overfitting']['detected']}`\n"
            "- Validation and test events are not used to fit parameters.\n",
            encoding="utf-8",
        )
        paths[language] = path
    return paths
