from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import zipfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from hydrolite.event_dataset import build_event_dataset, write_event_dataset
from hydrolite.flood_events import build_event_catalog, write_event_catalog
from hydrolite.hindcast_metrics import (
    aggregate_event_metrics,
    calculate_event_success_rate,
    calculate_hindcast_metrics,
    calculate_metric_worst_case,
    classify_hindcast_performance,
    summarize_metrics_by_event_magnitude,
    summarize_metrics_by_initial_condition,
    summarize_metrics_by_season,
)
from hydrolite.hydrologic_state import build_initial_state, write_initial_state_report
from hydrolite.hydrology import runoff_to_flow_cms
from hydrolite.io import read_reaches, read_subcatchments
from hydrolite.routing import route_reaches


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "hindcast_validation"
DEMO_SOURCE = PROJECT_ROOT / "data_demo" / "hindcast_validation"


def _project_data(project_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    project = Path(project_dir)
    candidates = [project / "data", project]
    sub_path = next((root / name for root in candidates for name in ("subbasins.csv", "subcatchments.csv") if (root / name).exists()), None)
    reach_path = next((root / name for root in candidates for name in ("reaches.csv", "reach.csv") if (root / name).exists()), None)
    if not sub_path or not reach_path:
        fallback = PROJECT_ROOT / "projects" / "qgis_workflow_project" / "data"
        sub_path, reach_path = fallback / "subbasins.csv", fallback / "reaches.csv"
    return read_subcatchments(sub_path), read_reaches(reach_path)


def _source_for_project(project_dir: str | Path) -> Path:
    project = Path(project_dir)
    for candidate in (project / "standardized" / "events_source", project / "data" / "hindcast_validation", project / "hindcast_validation"):
        if (candidate / "rainfall.csv").exists():
            return candidate
    return DEMO_SOURCE


def _catalog(source: Path = DEMO_SOURCE, output_root: Path = DEFAULT_OUTPUT) -> pd.DataFrame:
    path = output_root / "events" / "flood_event_catalog.csv"
    if path.exists():
        return pd.read_csv(path)
    frame = build_event_catalog(source)
    write_event_catalog(output_root / "events", frame)
    return frame


def _split(output_root: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    path = output_root / "splits" / "event_split.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    from hydrolite.event_split import split_events_chronologically, write_event_split_report
    result = split_events_chronologically(_catalog(output_root=output_root))
    write_event_split_report(output_root / "splits", result)
    return result


def _parameters(parameters: dict[str, Any] | None = None) -> dict[str, float]:
    return {
        "cn_delta": float((parameters or {}).get("cn_delta", 0.0)),
        "lag_multiplier": float((parameters or {}).get("lag_multiplier", 1.0)),
        "k_multiplier": float((parameters or {}).get("k_multiplier", 1.0)),
        "x_delta": float((parameters or {}).get("x_delta", 0.0)),
    }


def _apply_parameters(subbasins: pd.DataFrame, reaches: pd.DataFrame, parameters: dict[str, Any] | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    params = _parameters(parameters)
    sub, reach = subbasins.copy(), reaches.copy()
    sub["curve_number"] = (pd.to_numeric(sub["curve_number"], errors="raise") + params["cn_delta"]).clip(1, 100)
    sub["lag_hours"] = pd.to_numeric(sub["lag_hours"], errors="raise") * params["lag_multiplier"]
    reach["K_hours"] = pd.to_numeric(reach["K_hours"], errors="raise") * params["k_multiplier"]
    reach["X"] = (pd.to_numeric(reach["X"], errors="raise") + params["x_delta"]).clip(0, .5)
    return sub, reach


def _rainfall_for_model(frame: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    work = frame.copy()
    time_col = next(name for name in ("timestamp", "datetime", "time") if name in work)
    rain_col = next(name for name in ("rainfall_mm", "rain_mm", "precipitation_mm") if name in work)
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce", utc=True).dt.tz_convert(None)
    if "station_id" in work and work["station_id"].nunique() > 1:
        work = work.groupby(time_col, as_index=False)[rain_col].mean()
    else:
        work = work[[time_col, rain_col]]
    work = work.rename(columns={time_col: "time", rain_col: "rain_mm"}).dropna().sort_values("time")
    dt_hours = work["time"].diff().dt.total_seconds().median() / 3600 if len(work) > 1 else 1.0
    return work.reset_index(drop=True), float(dt_hours)


def _observed(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "observed_flow_cms"])
    time_col = next(name for name in ("timestamp", "datetime", "time") if name in frame)
    flow_col = next(name for name in ("flow_cms", "observed_streamflow_m3s", "outflow_cms") if name in frame)
    work = frame[[time_col, flow_col]].copy()
    work["timestamp"] = pd.to_datetime(work[time_col], errors="coerce", utc=True).dt.tz_convert(None)
    work["observed_flow_cms"] = pd.to_numeric(work[flow_col], errors="coerce")
    return work[["timestamp", "observed_flow_cms"]].dropna(subset=["timestamp"]).sort_values("timestamp")


def create_hindcast_config(project_dir: str | Path, events: Any) -> dict[str, Any]:
    ids = events["event_id"].astype(str).tolist() if isinstance(events, pd.DataFrame) else [str(item["event_id"]) for item in events]
    return {
        "project_dir": str(Path(project_dir).resolve()), "events": ids, "event_source": str(_source_for_project(project_dir)),
        "timeout_seconds_per_event": 120, "parameter_weighting": "equal", "synthetic_demo": _source_for_project(project_dir) == DEMO_SOURCE,
        "comparison_window": "warmup_start_to_analysis_end", "random_shuffle": False,
    }


def run_hydrolite_hindcast_event(
    project_dir: str | Path,
    event_dataset: dict[str, Any],
    parameters: dict[str, Any] | None,
    output_dir: str | Path,
    write_outputs: bool = True,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    event = event_dataset["event"]
    event_id = str(event["event_id"])
    try:
        rainfall, dt_hours = _rainfall_for_model(event_dataset["rainfall"])
        subbasins, reaches = _apply_parameters(*_project_data(project_dir), parameters)
        runoff = runoff_to_flow_cms(rainfall, subbasins, dt_hours)
        routed = route_reaches(runoff, reaches, dt_hours)
        initial = build_initial_state(event, event_dataset, project_dir)
        baseflow = float(initial.get("initial_baseflow_cms") or 0)
        decay = np.exp(-np.arange(len(routed)) * dt_hours / 48.0)
        simulated = routed[["time", "inflow_cms", "outflow_cms"]].copy()
        simulated["simulated_flow_cms"] = pd.to_numeric(simulated["outflow_cms"], errors="coerce") + baseflow * decay
        simulated["event_id"] = event_id
        observed = _observed(event_dataset["flow"])
        aligned = observed.merge(simulated.rename(columns={"time": "timestamp"}), on="timestamp", how="inner")
        metrics = calculate_hindcast_metrics(aligned["observed_flow_cms"], aligned["simulated_flow_cms"], aligned["timestamp"], dt_hours)
        inflow_volume = float(simulated["inflow_cms"].sum() * dt_hours * 3600)
        routed_volume = float(simulated["outflow_cms"].sum() * dt_hours * 3600)
        balance_error = routed_volume - inflow_volume
        balance_percent = 100 * balance_error / inflow_volume if inflow_volume else 0.0
        water_balance = pd.DataFrame([{
            "event_id": event_id, "inflow_volume_m3": inflow_volume, "routed_volume_m3": routed_volume,
            "balance_error_m3": balance_error, "balance_error_percent": balance_percent,
            "gate_status": "passed" if abs(balance_percent) <= 5 else "failed",
        }])
        if write_outputs:
            simulated.to_csv(output / "simulated_full.csv", index=False)
            aligned[["timestamp", "simulated_flow_cms"]].to_csv(output / "simulated_comparison.csv", index=False)
            observed.to_csv(output / "observed.csv", index=False)
            aligned.to_csv(output / "aligned.csv", index=False)
            with pd.ExcelWriter(output / "water_balance.xlsx") as writer:
                water_balance.to_excel(writer, sheet_name="event_balance", index=False)
            with pd.ExcelWriter(output / "event_metrics.xlsx") as writer:
                pd.DataFrame([{**metrics["summary"], "event_id": event_id}]).to_excel(writer, sheet_name="summary", index=False)
                metrics["metrics"].to_excel(writer, sheet_name="metrics", index=False)
                metrics["thresholds"].to_excel(writer, sheet_name="thresholds", index=False)
            charts = output / "charts"
            charts.mkdir(exist_ok=True)
            _plot_hydrograph(aligned, charts / "observed_simulated_hydrograph.png", event_id)
            _plot_event_rainfall(event_dataset["rainfall"], aligned, charts / "event_rainfall_flow.png", event_id)
        result = {
            "event_id": event_id, "run_status": "success", "synthetic_demo": bool(event_dataset.get("synthetic_demo")),
            "dt_hours": dt_hours, "parameters": _parameters(parameters), "initial_state": initial,
            "water_balance_error_percent": balance_percent, **metrics["summary"],
            "output_dir": str(output), "error_message": "",
        }
    except Exception as exc:  # noqa: BLE001
        result = {"event_id": event_id, "run_status": "failed", "synthetic_demo": bool(event_dataset.get("synthetic_demo")), "error_message": str(exc), "output_dir": str(output)}
    if write_outputs:
        write_hindcast_event_report(output, result)
    return result


def _plot_hydrograph(aligned: pd.DataFrame, path: Path, title: str) -> None:
    if aligned.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(aligned["timestamp"], aligned["observed_flow_cms"], label="Observed")
    ax.plot(aligned["timestamp"], aligned["simulated_flow_cms"], label="HydroLite")
    ax.set(title=title, ylabel="Flow (m3/s)")
    ax.grid(alpha=.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_event_rainfall(rainfall: pd.DataFrame, aligned: pd.DataFrame, path: Path, title: str) -> None:
    if rainfall.empty or aligned.empty:
        return
    time_col = next(name for name in ("timestamp", "datetime", "time") if name in rainfall)
    rain_col = next(name for name in ("rainfall_mm", "rain_mm", "precipitation_mm") if name in rainfall)
    rain = rainfall.copy()
    rain[time_col] = pd.to_datetime(rain[time_col], errors="coerce")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    ax1.bar(rain[time_col], pd.to_numeric(rain[rain_col], errors="coerce"), width=.03)
    ax1.set_ylabel("Rainfall (mm)")
    ax2.plot(aligned["timestamp"], aligned["observed_flow_cms"], label="Observed")
    ax2.plot(aligned["timestamp"], aligned["simulated_flow_cms"], label="HydroLite")
    ax2.set(ylabel="Flow (m3/s)", title=title)
    ax2.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run_hydrolite_hindcast_batch(
    project_dir: str | Path,
    events: Any = None,
    parameters: dict[str, Any] | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT / "hydrolite",
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source = _source_for_project(project_dir)
    catalog = events if isinstance(events, pd.DataFrame) else _catalog(source)
    event_ids = set(events) if isinstance(events, (list, tuple, set)) and events and isinstance(next(iter(events)), str) else None
    rows, states = [], []
    for event in catalog.to_dict("records"):
        if event_ids is not None and str(event["event_id"]) not in event_ids:
            continue
        dataset = build_event_dataset(event, source)
        write_event_dataset(DEFAULT_OUTPUT / "events" / "standardized" / str(event["event_id"]), dataset)
        state = build_initial_state(event, dataset, project_dir)
        states.append(state)
        rows.append(run_hydrolite_hindcast_event(project_dir, dataset, parameters, output / str(event["event_id"])))
    summary = summarize_hindcast_batch(rows)
    write_initial_state_report(DEFAULT_OUTPUT / "initial_states", states)
    write_hindcast_summary_report(output, summary)
    return summary


def validate_hindcast_event(result: dict[str, Any]) -> dict[str, Any]:
    errors = []
    if result.get("run_status") != "success":
        errors.append(result.get("error_message", "event failed"))
    if result.get("run_status") == "success" and abs(float(result.get("water_balance_error_percent", 100))) > 5:
        errors.append("water balance error exceeds 5%")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def summarize_hindcast_batch(results: list[dict[str, Any]] | pd.DataFrame) -> dict[str, Any]:
    frame = results.copy() if isinstance(results, pd.DataFrame) else pd.DataFrame(results)
    success = frame[frame.get("run_status", pd.Series(dtype=str)).eq("success")].copy()
    aggregate = aggregate_event_metrics(success)
    return {
        "status": "passed" if not frame.empty and len(success) else "failed",
        "events": frame, "aggregate": aggregate,
        "success_count": int(len(success)), "failure_count": int(len(frame) - len(success)),
        "success_rate": calculate_event_success_rate(frame), "worst_event": calculate_metric_worst_case(success),
        "performance_class": classify_hindcast_performance(aggregate),
    }


def write_hindcast_event_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for language, title in (("zh", "HydroLite 单事件回放报告"), ("en", "HydroLite Event Hindcast Report")):
        path = output / f"event_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Event: `{result.get('event_id')}`\n- Status: `{result.get('run_status')}`\n"
            f"- Synthetic demo: `{result.get('synthetic_demo')}`\n- NSE/KGE/PBIAS: `{result.get('NSE')}` / `{result.get('KGE')}` / `{result.get('PBIAS')}`\n"
            f"- Water balance error: `{result.get('water_balance_error_percent')}` %\n"
            "- This is event hindcast diagnostics, not an operational forecast.\n",
            encoding="utf-8",
        )
        paths[language] = path
    return paths


def write_hindcast_summary_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    events = result["events"]
    events.to_excel(output / "hydrolite_event_summary.xlsx", index=False)
    events.to_csv(output / "hydrolite_event_metrics.csv", index=False)
    manifest = {
        "status": result["status"], "success_count": result["success_count"], "failure_count": result["failure_count"],
        "performance_class": result["performance_class"], "synthetic_demo": bool(events.get("synthetic_demo", pd.Series(dtype=bool)).astype(bool).any()),
        "operational_forecast": False,
    }
    (output / "hydrolite_hindcast_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    paths = {}
    for language, title in (("zh", "HydroLite 多事件回放汇总"), ("en", "HydroLite Multi-event Hindcast Summary")):
        path = output / f"hydrolite_hindcast_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Success/failed: `{result['success_count']}` / `{result['failure_count']}`\n"
            f"- Diagnostic performance class: `{result['performance_class']}`\n"
            f"- Worst event: `{result.get('worst_event', {}).get('event_id', 'unavailable')}`\n"
            "- Reported classifications are software diagnostics, not engineering acceptance.\n",
            encoding="utf-8",
        )
        paths[language] = path
    return paths


def write_multi_event_summary(output_dir: str | Path, result: dict[str, Any], events: pd.DataFrame | None = None) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics = result["events"]
    catalog = events if events is not None else _catalog()
    aggregate = aggregate_event_metrics(metrics)
    worst = pd.DataFrame([result.get("worst_event", {})])
    with pd.ExcelWriter(output / "event_metrics.xlsx") as writer:
        metrics.to_excel(writer, sheet_name="events", index=False)
    with pd.ExcelWriter(output / "aggregate_metrics.xlsx") as writer:
        aggregate.to_excel(writer, sheet_name="aggregate", index=False)
    summarize_metrics_by_event_magnitude(catalog, metrics).to_excel(output / "performance_by_magnitude.xlsx", index=False)
    summarize_metrics_by_season(catalog, metrics).to_excel(output / "performance_by_season.xlsx", index=False)
    summarize_metrics_by_initial_condition(catalog, metrics).to_excel(output / "performance_by_initial_condition.xlsx", index=False)
    worst.to_excel(output / "worst_events.xlsx", index=False)
    return {"events": output / "event_metrics.xlsx", "aggregate": output / "aggregate_metrics.xlsx"}


def export_hindcast_validation_bundle(output_dir: str | Path = DEFAULT_OUTPUT) -> Path:
    root = Path(output_dir)
    target = root / "summary" / "hindcast_validation_bundle.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    allowed_roots = {"summary", "calibration", "lead_time", "mappings", "observations", "readiness", "splits", "initial_states"}
    forbidden = ("observed", "rainfall", "timeseries", "ensemble_state", "credential", "secret", "token", "data_raw", "external")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == target:
                continue
            relative = path.relative_to(root)
            lowered = relative.as_posix().lower()
            if relative.parts[0] not in allowed_roots or any(word in lowered for word in forbidden):
                continue
            if path.suffix.lower() not in {".xlsx", ".csv", ".json", ".yaml", ".md", ".png"}:
                continue
            archive.write(path, relative.as_posix())
        archive.writestr("bundle_manifest.json", json.dumps({"contains_raw_observations": False, "operational_validation": False}, indent=2))
    return target


def validate_hindcast_outputs(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = Path(output_dir)
    required = [
        root / "events" / "flood_event_catalog.xlsx",
        root / "hydrolite" / "hydrolite_event_summary.xlsx",
        root / "summary" / "model_validation_summary.xlsx",
        root / "summary" / "hindcast_validation_manifest.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    return {"status": "passed" if not missing else "failed", "missing": missing}


def prepare_hindcast_workspace(workspace_dir: str | Path, output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    from hydrolite.event_split import split_events_chronologically, write_event_split_report
    from hydrolite.hydrologic_observation_qc import (
        validate_rainfall_observations, validate_stage_observations,
        validate_streamflow_observations, write_observation_qc_report,
    )
    from hydrolite.observation_mapping import map_station_to_model_element, write_observation_mapping_report
    from hydrolite.validation_readiness import assess_hindcast_readiness, write_validation_readiness_report
    from hydrolite.event_dataset import load_event_source

    workspace, output = Path(workspace_dir), Path(output_dir)
    source = load_event_source(workspace)
    catalog = build_event_catalog(workspace)
    write_event_catalog(output / "events", catalog)
    split = split_events_chronologically(catalog)
    write_event_split_report(output / "splits", split)
    checks, corrections = [], []
    coverage = {}
    for name, function in (("rainfall", validate_rainfall_observations), ("flow", validate_streamflow_observations), ("stage", validate_stage_observations)):
        if source[name].empty:
            continue
        result = function(source[name])
        checks.append(result["checks"])
        corrections.append(result["corrections"])
        coverage[name] = result.get("coverage", 0)
    qc = {
        "status": "accepted_with_warnings" if checks else "missing_data",
        "checks": pd.concat(checks, ignore_index=True) if checks else pd.DataFrame(),
        "corrections": pd.concat(corrections, ignore_index=True) if corrections else pd.DataFrame(),
        "coverage": min(coverage.values()) if coverage else 0,
    }
    write_observation_qc_report(output / "observations", qc)
    _, reaches = _project_data(PROJECT_ROOT / "projects" / "qgis_workflow_project")
    project = {"reaches": reaches.to_dict("records"), "reservoirs": []}
    mapping_rows = [
        map_station_to_model_element(row, project)
        for row in source["stations"].to_dict("records")
        if str(row.get("variable", "")).lower() in {"flow", "stage", "water_level", "reservoir_stage"}
    ]
    write_observation_mapping_report(output / "mappings", mapping_rows)
    states = []
    for event in catalog.to_dict("records"):
        dataset = build_event_dataset(event, workspace)
        write_event_dataset(output / "events" / "standardized" / str(event["event_id"]), dataset)
        states.append(build_initial_state(event, dataset))
    write_initial_state_report(output / "initial_states", states)
    readiness = assess_hindcast_readiness(workspace)
    readiness.update({
        "mapping_count": len(mapping_rows),
        "low_confidence_mapping_count": sum(row["confidence"] == "low" for row in mapping_rows),
        "calibration_event_count": len(split["calibration"]),
        "validation_event_count": len(split["validation"]),
        "test_event_count": len(split["test"]),
    })
    write_validation_readiness_report(output / "readiness", readiness)
    catalog.assign(
        included_for_calibration=catalog["event_id"].astype(str).isin(split["calibration"]),
        included_for_validation=catalog["event_id"].astype(str).isin(split["validation"]),
        included_for_test=catalog["event_id"].astype(str).isin(split["test"]),
    ).to_excel(output / "events" / "event_quality_summary.xlsx", index=False)
    return {"status": "passed", "catalog": catalog, "split": split, "qc": qc, "mappings": pd.DataFrame(mapping_rows), "readiness": readiness}


def _simple_chart(frame: pd.DataFrame, path: Path, x: str, ys: list[str], title: str, kind: str = "line") -> Path | None:
    columns = [name for name in ys if name in frame]
    if frame.empty or x not in frame or not columns:
        return None
    clean = frame[[x, *columns]].copy()
    for name in columns:
        clean[name] = pd.to_numeric(clean[name], errors="coerce")
    if clean[columns].notna().sum().sum() == 0:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    positions = np.arange(len(clean))
    if kind == "bar":
        width = .8 / len(columns)
        for index, name in enumerate(columns):
            ax.bar(positions + index * width, clean[name], width=width, label=name)
        ax.set_xticks(positions + width * (len(columns) - 1) / 2, clean[x].astype(str), rotation=30)
    else:
        for name in columns:
            ax.plot(clean[x], clean[name], marker="o", label=name)
    ax.set_title(title)
    ax.grid(alpha=.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def generate_hindcast_charts(output_dir: str | Path = DEFAULT_OUTPUT) -> list[Path]:
    root = Path(output_dir)
    charts = root / "summary" / "charts"
    events_path = root / "hydrolite" / "hydrolite_event_summary.xlsx"
    catalog_path = root / "events" / "flood_event_catalog.csv"
    event_metrics = pd.read_excel(events_path) if events_path.exists() else pd.DataFrame()
    catalog = pd.read_csv(catalog_path) if catalog_path.exists() else pd.DataFrame()
    merged = event_metrics.merge(catalog[["event_id", "peak_flow_cms", "runoff_volume_m3", "quality_status"]], on="event_id", how="left", suffixes=("_sim", "_obs")) if not event_metrics.empty and not catalog.empty else pd.DataFrame()
    if not merged.empty:
        merged["simulated_peak_flow_cms"] = pd.to_numeric(merged["peak_flow_cms"], errors="coerce") * (1 + pd.to_numeric(merged["peak_flow_percent_error"], errors="coerce") / 100)
        merged["simulated_volume_m3"] = pd.to_numeric(merged["runoff_volume_m3"], errors="coerce") * (1 + pd.to_numeric(merged["volume_error_percent"], errors="coerce") / 100)
    outputs = [
        _simple_chart(merged, charts / "all_events_peak_comparison.png", "event_id", ["peak_flow_cms", "simulated_peak_flow_cms"], "Peak Flow by Event", "bar"),
        _simple_chart(merged, charts / "all_events_volume_comparison.png", "event_id", ["runoff_volume_m3", "simulated_volume_m3"], "Runoff Volume by Event", "bar"),
        _simple_chart(event_metrics, charts / "event_nse_distribution.png", "event_id", ["NSE"], "Event NSE", "bar"),
        _simple_chart(event_metrics, charts / "event_kge_distribution.png", "event_id", ["KGE"], "Event KGE", "bar"),
        _simple_chart(event_metrics, charts / "peak_error_by_event.png", "event_id", ["peak_flow_percent_error"], "Peak Error by Event", "bar"),
        _simple_chart(event_metrics, charts / "timing_error_by_event.png", "event_id", ["peak_timing_error_hr"], "Timing Error by Event", "bar"),
    ]
    assimilation_path = root / "assimilation" / "assimilation_metrics.xlsx"
    if assimilation_path.exists():
        assimilation = pd.read_excel(assimilation_path)
        outputs.extend([
            _simple_chart(assimilation, charts / "open_loop_vs_assimilated.png", "event_id", ["open_loop_NSE", "nudging_NSE", "enkf_NSE"], "Open-loop vs Assimilated NSE", "bar"),
            _simple_chart(assimilation, charts / "prior_posterior_ensemble.png", "event_id", ["prior_spread", "posterior_spread"], "Prior and Posterior Spread"),
        ])
    innovation_files = sorted((root / "assimilation").glob("*/assimilation_timeseries.csv"))
    if innovation_files:
        innovation = pd.concat([pd.read_csv(path) for path in innovation_files], ignore_index=True)
        outputs.append(_simple_chart(innovation, charts / "innovation_timeseries.png", "timestamp", ["innovation_cms"], "Assimilation Innovation"))
    stability_path = root / "calibration" / "parameter_stability.xlsx"
    if stability_path.exists():
        stability = pd.read_excel(stability_path)
        outputs.append(_simple_chart(stability, charts / "parameter_stability.png", "parameter", ["range", "stability_limit"], "Parameter Stability", "bar"))
    if not catalog.empty:
        quality = catalog.assign(quality_score=catalog["quality_status"].map({"accepted": 1, "accepted_with_warnings": .75, "needs_manual_review": .5, "rejected": 0}).fillna(.25))
        outputs.append(_simple_chart(quality, charts / "event_quality_matrix.png", "event_id", ["quality_score", "temporal_coverage"], "Event Quality", "bar"))
    return [path for path in outputs if path is not None]


def summarize_hindcast_validation(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    from hydrolite.validation_readiness import assess_hindcast_readiness
    root = Path(output_dir)
    hydrolite_path = root / "hydrolite" / "hydrolite_event_summary.xlsx"
    event_metrics = pd.read_excel(hydrolite_path) if hydrolite_path.exists() else pd.DataFrame()
    result = summarize_hindcast_batch(event_metrics) if not event_metrics.empty else summarize_hindcast_batch([])
    summary_dir = root / "summary"
    write_multi_event_summary(summary_dir, result)
    split = _split(root)
    event_metrics["split"] = event_metrics["event_id"].map({event_id: name for name in ("calibration", "validation", "test") for event_id in split.get(name, [])}) if not event_metrics.empty else pd.Series(dtype=str)
    split_rows = []
    for name in ("calibration", "validation", "test"):
        group = event_metrics[event_metrics.get("split", pd.Series(dtype=str)).eq(name)]
        split_rows.append({
            "split": name, "event_count": len(group), "NSE": pd.to_numeric(group.get("NSE"), errors="coerce").median(),
            "KGE": pd.to_numeric(group.get("KGE"), errors="coerce").median(), "PBIAS": pd.to_numeric(group.get("PBIAS"), errors="coerce").median(),
        })
    readiness_file = root / "readiness" / "hindcast_readiness.json"
    readiness = json.loads(readiness_file.read_text(encoding="utf-8")) if readiness_file.exists() else assess_hindcast_readiness(DEMO_SOURCE)
    assimilation_file = root / "assimilation" / "assimilation_metrics.xlsx"
    assimilation = pd.read_excel(assimilation_file) if assimilation_file.exists() else pd.DataFrame()
    overview = pd.DataFrame([{
        "status": result["status"], "validation_level": readiness["validation_level"],
        "demo_validation_level": readiness.get("demo_validation_level"), "event_count": len(event_metrics),
        "successful_events": result["success_count"], "failed_events": result["failure_count"],
        "performance_class": result["performance_class"], "operational_candidate": False, "operational_verified": False,
    }])
    with pd.ExcelWriter(summary_dir / "model_validation_summary.xlsx") as writer:
        overview.to_excel(writer, sheet_name="overview", index=False)
        pd.DataFrame(split_rows).to_excel(writer, sheet_name="split_metrics", index=False)
        event_metrics.to_excel(writer, sheet_name="event_metrics", index=False)
        assimilation.to_excel(writer, sheet_name="assimilation", index=False)
    charts = generate_hindcast_charts(root)
    worst = result.get("worst_event", {})
    for language, title in (("zh", "多事件洪水回放与同化验证报告"), ("en", "Multi-event Flood Hindcast and Assimilation Validation Report")):
        path = summary_dir / f"model_validation_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Validation level: `{readiness['validation_level']}`\n"
            f"- Demo validation level: `{readiness.get('demo_validation_level')}`\n"
            f"- HydroLite success/failed: `{result['success_count']}` / `{result['failure_count']}`\n"
            f"- Worst event: `{worst.get('event_id', 'unavailable')}`; NSE `{worst.get('NSE', 'unavailable')}`\n"
            f"- Assimilation events: `{len(assimilation)}`\n"
            "- Analysis uses observations at the analysis time and is not a pure forecast.\n"
            "- Synthetic demo metrics are excluded from real validation and operational claims.\n"
            "- These are software diagnostics, not engineering acceptance or operational verification.\n",
            encoding="utf-8",
        )
    manifest = {
        "status": result["status"], "validation_level": readiness["validation_level"],
        "synthetic_demo": bool(event_metrics.get("synthetic_demo", pd.Series(dtype=bool)).astype(bool).any()),
        "event_count": len(event_metrics), "successful_events": result["success_count"],
        "charts": [str(path.relative_to(root)) for path in charts], "operational_candidate": False,
        "operational_verified": False,
    }
    (summary_dir / "hindcast_validation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    bundle = export_hindcast_validation_bundle(root)
    return {"status": result["status"], "overview": overview, "split_metrics": pd.DataFrame(split_rows), "event_metrics": event_metrics, "charts": charts, "bundle": bundle, "readiness": readiness}
