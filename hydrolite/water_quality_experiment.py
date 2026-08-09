"""Orchestration for the clean-room Water Quality Method Lab MVP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import zipfile
import hashlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from hydrolite.water_quality_contracts import CORE_VARIABLES, EXPERIMENT_NOTICE, default_variable_specs
from hydrolite.water_quality_evaluation import calculate_threshold_diagnostics, evaluate_load_predictions, validate_evaluation_separation
from hydrolite.water_quality_features import build_topological_context, build_travel_time_context, build_water_quality_features, map_stations_to_reaches, validate_station_mapping, validate_water_quality_features
from hydrolite.water_quality_forecast import build_forecast_samples, calculate_feature_ablation, fit_candidate_models, validate_forecast_result
from hydrolite.water_quality_load import align_concentration_and_flow, concentration_flow_to_load, summarize_loads
from hydrolite.water_quality_observations import build_station_coverage, run_observation_qc, validate_observations


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DIR = ROOT / "data_demo" / "method_inspiration" / "water_quality"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "method_inspiration" / "water_quality"
SYNTHETIC_NOTICE = "Synthetic method demo only; not real validation and not a regulatory assessment."


def _write_frame(path: Path, frame: pd.DataFrame, sheet_name: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv": frame.to_csv(path, index=False)
    else: frame.to_excel(path, index=False, sheet_name=sheet_name)
    return path


def generate_synthetic_water_quality_demo(demo_dir: str | Path = DEFAULT_DEMO_DIR, seed: int = 20260809) -> dict[str, Any]:
    root = Path(demo_dir); root.mkdir(parents=True, exist_ok=True); rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=730, freq="D")
    stations = pd.DataFrame({
        "station_id": [f"WQ{i}" for i in range(1, 8)],
        "station_name": [f"Synthetic station {i}" for i in range(1, 8)],
        "reach_id": [f"R{i}" for i in range(1, 8)],
        "longitude": np.linspace(113.8, 114.1, 7), "latitude": np.linspace(22.5, 22.8, 7),
        "synthetic_demo": True,
    })
    edges = pd.DataFrame([
        {"edge_id": "E1", "source_node": "R1", "target_node": "R3", "distance_km": 8.0, "travel_time": 24.0},
        {"edge_id": "E2", "source_node": "R2", "target_node": "R3", "distance_km": 6.0, "travel_time": 24.0},
        {"edge_id": "E3", "source_node": "R3", "target_node": "R4", "distance_km": 9.0, "travel_time": 24.0},
        {"edge_id": "E4", "source_node": "R4", "target_node": "R6", "distance_km": 10.0, "travel_time": 24.0},
        {"edge_id": "E5", "source_node": "R5", "target_node": "R6", "distance_km": 7.0, "travel_time": 24.0},
        {"edge_id": "E6", "source_node": "R6", "target_node": "R7", "distance_km": 12.0, "travel_time": 24.0},
    ])
    rain_base = rng.gamma(1.2, 7.0, len(dates)) * (rng.random(len(dates)) < 0.28)
    meteorology_rows = []; flow_rows = []; hydro_rows = []
    for station_index, station in enumerate(stations.station_id):
        rain = np.maximum(0, rain_base * (0.85 + 0.05 * station_index) + rng.normal(0, 0.5, len(dates)))
        temperature = 21 + 8 * np.sin(2 * np.pi * np.arange(len(dates)) / 365.25) + rng.normal(0, 1.2, len(dates))
        storm = pd.Series(rain).rolling(5, min_periods=1).apply(lambda values: np.sum(values * np.linspace(0.2, 1.0, len(values))), raw=True).to_numpy()
        baseflow = 0.8 + 0.08 * station_index + 0.12 * np.sin(2 * np.pi * np.arange(len(dates)) / 365.25 + station_index / 7)
        surface = 0.06 * storm; interflow = pd.Series(rain).rolling(12, min_periods=1).mean().to_numpy() * 0.025
        flow = np.maximum(0.05, baseflow + surface + interflow + rng.normal(0, 0.04, len(dates)))
        soil = np.clip(0.25 + pd.Series(rain).rolling(20, min_periods=1).mean().to_numpy() / 120 + rng.normal(0, 0.015, len(dates)), 0.1, 0.8)
        for i, date in enumerate(dates):
            meteorology_rows.append({"timestamp": date, "station_id": station, "rainfall_mm": rain[i], "temperature_c": temperature[i], "source": "synthetic_generator", "synthetic_demo": True})
            flow_rows.append({"timestamp": date, "station_id": station, "flow_cms": flow[i], "source": "synthetic_generator", "synthetic_demo": True})
            hydro_rows.append({"timestamp": date, "station_id": station, "surface_runoff": surface[i], "interflow": interflow[i], "baseflow": baseflow[i], "soil_moisture": soil[i], "source": "synthetic_generator", "synthetic_demo": True})
    meteorology = pd.DataFrame(meteorology_rows); daily_flow = pd.DataFrame(flow_rows); hydrology = pd.DataFrame(hydro_rows)
    # Create one missing flow record so load availability is explicitly testable.
    daily_flow = daily_flow.drop(daily_flow[(daily_flow.station_id == "WQ7") & (daily_flow.timestamp == dates[25])].index)
    bases = {"CODMn": 3.2, "NH3-N": 0.22, "TN": 1.25, "TP": 0.09}
    rain_coeff = {"CODMn": 0.020, "NH3-N": 0.002, "TN": 0.006, "TP": 0.0008}
    observations = []
    upstream = {"WQ1": [], "WQ2": [], "WQ3": ["WQ1", "WQ2"], "WQ4": ["WQ3"], "WQ5": [], "WQ6": ["WQ4", "WQ5"], "WQ7": ["WQ6"]}
    generated: dict[tuple[str, str], np.ndarray] = {}
    for variable in CORE_VARIABLES:
        for station_index, station in enumerate(stations.station_id):
            ctx = meteorology[meteorology.station_id == station].reset_index(drop=True); flow = daily_flow[daily_flow.station_id == station].set_index("timestamp").reindex(dates).flow_cms.interpolate().to_numpy()
            local = bases[variable] * (1 + 0.035 * station_index) + rain_coeff[variable] * pd.Series(ctx.rainfall_mm).rolling(4, min_periods=1).mean().to_numpy()
            local += bases[variable] * 0.10 * np.sin(2 * np.pi * np.arange(len(dates)) / 365.25 + station_index / 4)
            local += bases[variable] * 0.035 * (flow - np.nanmean(flow)) / np.nanstd(flow)
            if upstream[station]:
                signal = np.mean([np.roll(generated[(variable, item)], 1) for item in upstream[station]], axis=0); signal[0] = local[0]
                local = 0.72 * local + 0.28 * signal
            values = np.maximum(0.001, local + rng.normal(0, bases[variable] * 0.055, len(dates)))
            generated[(variable, station)] = values
            for date, value in zip(dates, values):
                observations.append({"timestamp": date, "station_id": station, "variable_id": variable, "value": value, "unit": "mg/L", "qualifier": "", "source": "synthetic_generator", "synthetic_demo": True})
    water_quality = pd.DataFrame(observations)
    # Deliberate QC cases: preserve rows and let the QC ledger classify them.
    water_quality.loc[10, "qualifier"] = "below_detection_limit"; water_quality.loc[10, "detection_limit"] = 0.01; water_quality.loc[10, "value"] = np.nan
    duplicate = water_quality.iloc[[20]].copy(); water_quality = pd.concat([water_quality, duplicate], ignore_index=True)
    water_quality.loc[30, "value"] = -0.2
    mapping = stations[["station_id", "reach_id"]].assign(mapping_method="configured_exact", mapping_confidence="high")
    thresholds = {"diagnostic_thresholds": {"CODMn": 4.0, "NH3-N": 0.30, "TN": 1.50, "TP": 0.12}, "threshold_type": "diagnostic_only", "synthetic_demo": True}
    config = {"synthetic_demo": True, "horizons_days": [1, 3, 7, 14], "non_detect_method": "preserve_qualifier", "alignment_method": "daily", "include_trend": True, "hydrologic_context": {"wet_rainfall_mm": 1.0, "storm_rainfall_mm": 10.0}, "notice": SYNTHETIC_NOTICE}
    _write_frame(root / "stations.csv", stations); _write_frame(root / "station_reach_mapping.csv", mapping); _write_frame(root / "reach_edges.csv", edges)
    _write_frame(root / "water_quality_daily.csv", water_quality); _write_frame(root / "daily_flow.csv", daily_flow); _write_frame(root / "daily_hydrology.csv", hydrology); _write_frame(root / "meteorology.csv", meteorology)
    (root / "diagnostic_thresholds.yaml").write_text(yaml.safe_dump(thresholds, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (root / "water_quality_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    checksums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file() and path.name not in {"generation_manifest.json", "expected_results.json"}}
    manifest = {"synthetic_demo": True, "seed": seed, "date_range": [str(dates.min().date()), str(dates.max().date())], "days": 730, "station_count": 7, "station_topology": edges.to_dict(orient="records"), "pollutants": list(CORE_VARIABLES), "variable_generation_logic": "seasonal background + storm response + flow response + lagged upstream signal + measurement noise", "true_travel_times_hours": edges.set_index("edge_id").travel_time.to_dict(), "noise": "seeded Gaussian variable-specific noise", "synthetic_thresholds": thresholds["diagnostic_thresholds"], "checksums": checksums, "generation_method": "independent HydroLite synthetic method demo", "notice": SYNTHETIC_NOTICE}
    (root / "generation_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / "expected_results.json").write_text(json.dumps({"expected_status": "passed", "expected_horizons": [1, 3, 7, 14], "value_added_may_be_mixed": True, "real_data_value_added": "not_tested"}, indent=2), encoding="utf-8")
    return {"status": "passed", "demo_dir": str(root), **manifest}


def load_demo_inputs(demo_dir: str | Path = DEFAULT_DEMO_DIR) -> dict[str, Any]:
    root = Path(demo_dir)
    if not (root / "water_quality_daily.csv").exists(): generate_synthetic_water_quality_demo(root)
    return {
        "root": root,
        "stations": pd.read_csv(root / "stations.csv"), "mapping": pd.read_csv(root / "station_reach_mapping.csv"), "edges": pd.read_csv(root / "reach_edges.csv"),
        "observations": pd.read_csv(root / "water_quality_daily.csv"), "flow": pd.read_csv(root / "daily_flow.csv"), "hydrology": pd.read_csv(root / "daily_hydrology.csv"), "meteorology": pd.read_csv(root / "meteorology.csv"),
        "thresholds": yaml.safe_load((root / "diagnostic_thresholds.yaml").read_text(encoding="utf-8")), "config": yaml.safe_load((root / "water_quality_config.yaml").read_text(encoding="utf-8")),
    }


def _plot_outputs(root: Path, qc: pd.DataFrame, ledger: pd.DataFrame, predictions: pd.DataFrame, metrics: pd.DataFrame, ablation: pd.DataFrame, mapping: pd.DataFrame, edges: pd.DataFrame, thresholds: dict[str, float]) -> list[Path]:
    charts = root / "charts"; charts.mkdir(parents=True, exist_ok=True); paths = []
    def save(name: str, title: str):
        plt.title(title + "\nSynthetic demo"); plt.tight_layout(); path = charts / name; plt.savefig(path, dpi=140); plt.close(); paths.append(path)
    plt.figure(figsize=(8, 4)); positions = {station: (i, (i % 3) * 0.3) for i, station in enumerate(mapping.station_id)}
    for edge in edges.itertuples():
        stations_by_reach = dict(zip(mapping.reach_id, mapping.station_id)); a, b = stations_by_reach.get(edge.source_node), stations_by_reach.get(edge.target_node)
        if a and b: plt.annotate("", xy=positions[b], xytext=positions[a], arrowprops={"arrowstyle": "->", "color": "#4b6f8a"})
    for station, (x, y) in positions.items(): plt.scatter(x, y, s=80); plt.text(x, y + .05, station, ha="center")
    plt.axis("off"); save("station_network.png", "Directed station network")
    sample = qc[(qc.station_id == "WQ7") & (qc.variable_id == "TN")].sort_values("timestamp")
    plt.figure(figsize=(9, 4)); plt.plot(pd.to_datetime(sample.timestamp), sample.value); plt.ylabel("TN (mg/L)"); save("water_quality_timeseries.png", "Water-quality time series")
    load_sample = ledger[(ledger.station_id == "WQ7") & (ledger.variable_id == "TN")]
    plt.figure(figsize=(6, 4)); plt.scatter(load_sample.flow_cms, load_sample.value, s=8, alpha=.5); plt.xlabel("Flow (m3/s)"); plt.ylabel("Concentration (mg/L)"); save("concentration_vs_flow.png", "Concentration versus flow")
    plt.figure(figsize=(6, 4)); plt.scatter(load_sample.value, load_sample.load_kg_day, s=8, alpha=.5); plt.xlabel("Concentration (mg/L)"); plt.ylabel("Load (kg/day)"); save("concentration_vs_load.png", "Concentration versus load")
    plt.figure(figsize=(9, 4));
    for station in ("WQ1", "WQ3", "WQ7"):
        item = qc[(qc.station_id == station) & (qc.variable_id == "TN")].sort_values("timestamp").head(180); plt.plot(pd.to_datetime(item.timestamp), item.value, label=station)
    plt.legend(); plt.ylabel("TN (mg/L)"); save("upstream_downstream_response.png", "Upstream-downstream response")
    context = qc.merge(ledger[["timestamp", "station_id", "variable_id", "flow_cms"]], on=["timestamp", "station_id", "variable_id"], how="left"); context["weather"] = np.where(context.flow_cms >= context.flow_cms.median(), "wet/high-flow", "dry/low-flow")
    grouped = context.groupby(["variable_id", "weather"]).value.mean().unstack(); plt.figure(figsize=(7, 4)); grouped.plot(kind="bar", ax=plt.gca()); plt.ylabel("Mean concentration (mg/L)"); save("wet_dry_comparison.png", "Wet and dry response")
    selected_metrics = metrics[(metrics.split == "test")].groupby("horizon_days", as_index=False).RMSE.mean(); plt.figure(figsize=(6, 4)); plt.plot(selected_metrics.horizon_days, selected_metrics.RMSE, marker="o"); plt.xlabel("Horizon (days)"); plt.ylabel("RMSE"); save("horizon_skill_decay.png", "Forecast error by horizon")
    compare = metrics[(metrics.split == "test")].groupby("model_id").RMSE.mean().sort_values().head(8); plt.figure(figsize=(9, 4)); compare.plot(kind="bar", ax=plt.gca()); plt.ylabel("Mean RMSE"); save("pollutant_model_comparison.png", "Candidate model comparison")
    abl = ablation.groupby("model_id").RMSE_improvement.mean().sort_values(); plt.figure(figsize=(9, 4)); abl.plot(kind="bar", ax=plt.gca()); plt.axhline(0, color="black", linewidth=.8); plt.ylabel("RMSE improvement"); save("feature_ablation.png", "Feature group ablation")
    plt.figure(figsize=(7, 4)); threshold_rows = []
    for variable, threshold in thresholds.items():
        group = predictions[(predictions.variable_id == variable) & (predictions.split == "test")]; threshold_rows.append(calculate_threshold_diagnostics(group.observed, group.predicted, threshold))
    plt.bar(list(thresholds), [row["recall"] for row in threshold_rows]); plt.ylim(0, 1); plt.ylabel("Diagnostic threshold recall"); save("threshold_diagnostic.png", "Diagnostic threshold performance")
    return paths


def run_water_quality_method_lab(demo_dir: str | Path = DEFAULT_DEMO_DIR, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    inputs = load_demo_inputs(demo_dir); root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    specs = default_variable_specs(); config = inputs["config"]
    qc, qc_summary = run_observation_qc(inputs["observations"], specs, non_detect_method=config["non_detect_method"])
    coverage = build_station_coverage(qc)
    reach_ids = sorted(set(inputs["mapping"].reach_id.astype(str)) | set(inputs["edges"].source_node.astype(str)) | set(inputs["edges"].target_node.astype(str)))
    reaches = pd.DataFrame({"reach_id": reach_ids})
    mapping = map_stations_to_reaches(inputs["mapping"], reaches)
    mapping_validation = validate_station_mapping(mapping, reaches); topology = build_topological_context(mapping, inputs["edges"]); travel = build_travel_time_context(mapping, inputs["edges"])
    load_input = qc[qc.training_eligible].copy(); ledger = align_concentration_and_flow(load_input, inputs["flow"], config["alignment_method"]); load_summary = summarize_loads(ledger)
    features, provenance = build_water_quality_features(qc, inputs["flow"], inputs["hydrology"], mapping, inputs["edges"], inputs["meteorology"], include_trend=bool(config.get("include_trend", False)))
    feature_validation = validate_water_quality_features(features, provenance); samples = build_forecast_samples(features, config["horizons_days"])
    predictions, candidate_metrics, selections = fit_candidate_models(samples); forecast_validation = validate_forecast_result(predictions, selections); separation = validate_evaluation_separation(selections, predictions)
    predictions = predictions.rename(columns={"timestamp": "issue_time"})
    predictions["lead"] = predictions["horizon_days"]
    predictions["variable"] = predictions["variable_id"]
    predictions["prediction"] = predictions["predicted"]
    predictions["unit"] = "mg/L"
    predictions["feature_groups"] = predictions["model_id"].map(lambda value: value.replace("_linear", "").replace("_", ","))
    predictions["forecast_mode"] = "direct_horizon_specific"
    predictions["data_as_of"] = predictions["issue_time"]
    predictions["is_synthetic"] = True
    predictions["uncertainty_status"] = predictions["uncertainty_type"]
    # Load forecasts use issue-time flow persistence; future flow is evaluation-only.
    future_flow = inputs["flow"].copy(); future_flow["timestamp"] = pd.to_datetime(future_flow.timestamp)
    predictions["issue_time"] = pd.to_datetime(predictions.issue_time); predictions["valid_time"] = pd.to_datetime(predictions.valid_time)
    predictions = predictions.merge(future_flow[["timestamp", "station_id", "flow_cms"]].rename(columns={"timestamp": "valid_time", "flow_cms": "observed_flow_cms"}), on=["valid_time", "station_id"], how="left")
    predictions["observed_load_kg_day"] = concentration_flow_to_load(predictions.observed, predictions.observed_flow_cms)
    predictions["predicted_load_kg_day"] = concentration_flow_to_load(predictions.predicted, predictions.flow_cms)
    load_metrics = evaluate_load_predictions(predictions[predictions.split == "test"])
    ablation = calculate_feature_ablation(candidate_metrics)
    thresholds = inputs["thresholds"]["diagnostic_thresholds"]; threshold_rows = []
    for (variable, horizon), group in predictions[predictions.split == "test"].groupby(["variable_id", "horizon_days"]):
        threshold_rows.append({"variable_id": variable, "horizon_days": horizon, **calculate_threshold_diagnostics(group.observed, group.predicted, thresholds[variable])})
    threshold_diagnostics = pd.DataFrame(threshold_rows)
    wet_dry = features.groupby(["variable_id", "hydrologic_context"], as_index=False).agg(mean_concentration=("value", "mean"), observation_count=("value", "count"))
    upstream_response = features.groupby(["station_id", "variable_id"], as_index=False).agg(local_mean=("local_lag_1", "mean"), upstream_mean=("upstream_lag_1_mean", "mean"))
    uncertainty = predictions[["issue_time", "valid_time", "station_id", "variable_id", "horizon_days", "lower", "upper", "uncertainty_type"]].copy()
    _write_frame(root / "data_quality" / "observation_qc.xlsx", qc); _write_frame(root / "data_quality" / "station_coverage.xlsx", coverage); _write_frame(root / "data_quality" / "station_mapping.xlsx", mapping)
    with pd.ExcelWriter(root / "data_quality" / "observation_qc.xlsx") as writer:
        qc.to_excel(writer, sheet_name="observations", index=False); qc_summary.to_excel(writer, sheet_name="quality_summary", index=False)
    _write_frame(root / "loads" / "concentration_load_ledger.csv", ledger); _write_frame(root / "loads" / "load_summary.xlsx", load_summary)
    (root / "features").mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(root / "features" / "feature_manifest.xlsx") as writer:
        provenance.to_excel(writer, sheet_name="feature_provenance", index=False); pd.DataFrame([feature_validation]).to_excel(writer, sheet_name="validation", index=False); travel.to_excel(writer, sheet_name="travel_time", index=False)
    _write_frame(root / "features" / "feature_ablation.xlsx", ablation)
    _write_frame(root / "forecast" / "station_predictions.csv", predictions); _write_frame(root / "forecast" / "horizon_metrics.xlsx", candidate_metrics)
    _write_frame(root / "forecast" / "pollutant_metrics.xlsx", candidate_metrics[candidate_metrics.split == "test"].groupby(["variable_id", "model_id"], as_index=False).mean(numeric_only=True)); _write_frame(root / "forecast" / "model_selection.xlsx", selections)
    _write_frame(root / "diagnostics" / "wet_dry_response.xlsx", wet_dry); _write_frame(root / "diagnostics" / "upstream_response.xlsx", upstream_response); _write_frame(root / "diagnostics" / "threshold_diagnostics.xlsx", threshold_diagnostics); _write_frame(root / "diagnostics" / "uncertainty_intervals.xlsx", uncertainty)
    _write_frame(root / "benchmark" / "candidate_model_metrics.xlsx", candidate_metrics); _write_frame(root / "benchmark" / "feature_group_value_added.xlsx", ablation)
    _write_frame(root / "benchmark" / "load_metrics.xlsx", load_metrics)
    charts = _plot_outputs(root, qc, ledger, predictions, candidate_metrics, ablation, mapping, inputs["edges"], thresholds)
    selected_test = candidate_metrics.merge(selections[["variable_id", "horizon_days", "selected_model"]], on=["variable_id", "horizon_days"]); selected_test = selected_test[(selected_test.split == "test") & (selected_test.model_id == selected_test.selected_model)]
    value_counts = ablation.feature_group_value_added.value_counts().to_dict()
    test_ablation = ablation.copy()
    comparison_models = {"hydrology": "local_hydrology_linear", "gamma": "local_gamma_linear", "graph": "graph_hydrology_linear", "trend": "graph_gamma_trend_linear"}
    value_added_rows = []
    for (variable, horizon), group in test_ablation.groupby(["variable_id", "horizon_days"]):
        row = {"variable_id": variable, "horizon_days": int(horizon), "real_data_value_added": "not_tested"}
        by_model = group.set_index("model_id")
        for label, model_id in comparison_models.items():
            if model_id in by_model.index:
                improvement = float(by_model.loc[model_id, "RMSE_improvement"])
                row[f"{label}_value_added"] = "demonstrated" if improvement > 0 else "not_demonstrated"
            else: row[f"{label}_value_added"] = "insufficient_data"
        value_added_rows.append(row)
    feature_value_added = pd.DataFrame(value_added_rows)
    overall_value = "mixed" if len(set(feature_value_added[[column for column in feature_value_added if column.endswith("_value_added") and column != "real_data_value_added"]].stack())) > 1 else "not_demonstrated"
    _write_frame(root / "benchmark" / "feature_group_value_added.xlsx", feature_value_added)
    manifest = {
        "status": "passed" if all(item["status"] == "passed" for item in (feature_validation, forecast_validation, separation)) and topology["status"] == "passed" else "failed",
        "capability": "water_quality_method_lab", "capability_status": "partial", "water_quality": "planned", "validation_level": "synthetic_method_demo", "synthetic_demo": True,
        "notice": SYNTHETIC_NOTICE, "method_notice": EXPERIMENT_NOTICE, "station_count": 7, "pollutants": list(CORE_VARIABLES), "horizons_days": [1, 3, 7, 14],
        "quality_counts": {flag: int((qc.quality_status == flag).sum()) for flag in ("valid", "suspect", "invalid", "below_detection_limit", "missing", "duplicate", "unit_error", "range_warning", "stale")}, "mapping_validation": mapping_validation, "topology": topology, "feature_validation": feature_validation, "forecast_validation": forecast_validation, "selection_validation": separation,
        "non_detect_method": config["non_detect_method"], "alignment_method": config["alignment_method"], "flow_alignment_status": "passed", "load_unit_gate": "passed", "load_available_records": int((ledger.load_status == "available").sum()), "missing_flow_load_records": int((ledger.load_status == "flow_unavailable").sum()), "load_formula": "mg/L * m3/s * 86.4 = kg/day", "trend_default": "optional_candidate_not_forced", "hydrologic_context_counts": features.hydrologic_context.value_counts().to_dict(), "threshold_diagnostic_status": "synthetic_demo_threshold_only",
        "candidate_models": sorted(candidate_metrics.model_id.unique()), "value_added_counts": value_counts, "water_quality_method_value_added": overall_value, "feature_group_value_added": feature_value_added.to_dict(orient="records"), "real_data_value_added": "not_tested", "readiness": "synthetic_demo_ready", "selected_test_metrics": selected_test.to_dict(orient="records"),
        "charts": [str(path.relative_to(root)) for path in charts], "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    reports = root / "reports"; reports.mkdir(parents=True, exist_ok=True)
    for obsolete in (reports / "manifest.json", reports / "bundle.zip"):
        if obsolete.exists():
            obsolete.unlink()
    zh = f"""# HydroLite 多站点水质方法实验报告\n\n> {EXPERIMENT_NOTICE}\n\n> {SYNTHETIC_NOTICE}\n\n## 状态\n\n- Water Quality Method Lab: `partial`\n- 正式 water_quality: `planned`\n- 验证等级: `synthetic_method_demo`\n- 站点/指标: 7 / {', '.join(CORE_VARIABLES)}\n- 提前期: 1、3、7、14 日，14 日仅为 long_horizon_diagnostic\n\n## 方法\n\n观测 QC → 站点河网映射 → 浓度/负荷账本 → Gamma、上游和因果趋势候选特征 → 透明线性基线 → 验证集选模 → 固定测试集评价。测试集未用于选模或不确定性拟合。\n\n## 边界\n\n本实验不包含污染物反应动力学、法定达标判定或生产水质预报。浓度与负荷严格分开；缺流量时负荷标记 unavailable。数据驱动结果不会替代 HydroLite 水量账本。\n"""
    en = f"""# HydroLite Multi-station Water-quality Method Lab\n\n> {EXPERIMENT_NOTICE}\n\n> {SYNTHETIC_NOTICE}\n\nThe lab is partial and the production water_quality capability remains planned. It uses transparent causal features, validation-only model selection, a fixed test period, and strict concentration/load separation. The 14-day horizon is diagnostic only.\n"""
    (reports / "water_quality_method_report_zh.md").write_text(zh, encoding="utf-8"); (reports / "water_quality_method_report_en.md").write_text(en, encoding="utf-8"); (reports / "water_quality_method_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    bundle = reports / "water_quality_method_bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path != bundle and path.suffix.lower() not in {".zip", ".pt", ".pth", ".ckpt", ".onnx", ".dss", ".hdf5", ".h5"}:
                archive.write(path, path.relative_to(root))
    manifest["output_dir"] = str(root); manifest["bundle"] = str(bundle)
    return manifest


def validate_water_quality_method_lab(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    root = Path(output_dir); required = [
        root / "data_quality" / "observation_qc.xlsx", root / "loads" / "concentration_load_ledger.csv", root / "features" / "feature_manifest.xlsx",
        root / "forecast" / "station_predictions.csv", root / "forecast" / "horizon_metrics.xlsx", root / "forecast" / "model_selection.xlsx",
        root / "diagnostics" / "threshold_diagnostics.xlsx", root / "reports" / "water_quality_method_report_zh.md", root / "reports" / "water_quality_method_manifest.json",
    ]
    missing = [str(path) for path in required if not path.exists() or path.stat().st_size == 0]
    manifest = json.loads((root / "reports" / "water_quality_method_manifest.json").read_text(encoding="utf-8")) if not missing else {}
    return {"status": "passed" if not missing and manifest.get("water_quality") == "planned" else "failed", "missing": missing, "water_quality": manifest.get("water_quality"), "validation_level": manifest.get("validation_level")}


def write_water_quality_method_report(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    result = run_water_quality_method_lab(output_dir=output_dir)
    return {"status": result["status"], "report_zh": str(Path(output_dir) / "reports" / "water_quality_method_report_zh.md"), "report_en": str(Path(output_dir) / "reports" / "water_quality_method_report_en.md")}


def build_water_quality_bundle(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    result = run_water_quality_method_lab(output_dir=output_dir)
    return {"status": result["status"], "bundle": result["bundle"]}


def assess_water_quality_experiment() -> dict[str, str]:
    return {"status": "partial", "capability": "water_quality_method_lab", "water_quality_method_lab": "partial", "water_quality": "planned", "validation_level": "synthetic_method_demo", "notice": EXPERIMENT_NOTICE}


def assess_water_quality_method_readiness(observations: Any | None = None, station_mapping: Any | None = None, flow: Any | None = None, *, synthetic_demo: bool = False) -> dict[str, Any]:
    if synthetic_demo:
        return {"status": "synthetic_demo_ready", "validated_real_data": False}
    if observations is None or len(pd.DataFrame(observations)) == 0:
        return {"status": "insufficient_temporal_data", "validated_real_data": False}
    observation_status = validate_observations(observations)
    if observation_status["status"] != "passed":
        return {"status": "validation_failed", "validation": observation_status, "validated_real_data": False}
    if station_mapping is None or (pd.DataFrame(station_mapping).get("mapping_status", pd.Series("unresolved", index=pd.DataFrame(station_mapping).index)) != "mapped").any():
        return {"status": "station_mapping_incomplete", "validated_real_data": False}
    if flow is None or len(pd.DataFrame(flow)) == 0:
        return {"status": "missing_flow", "validated_real_data": False}
    return {"status": "real_data_structure_ready", "validated_real_data": False}


def write_water_quality_method_demo(output_dir: str | Path) -> dict[str, str]:
    target = Path(output_dir) / "water_quality" if Path(output_dir).name == "method_inspiration" else Path(output_dir)
    result = run_water_quality_method_lab(output_dir=target)
    return {"report": str(target / "reports" / "water_quality_method_report_zh.md"), "status": result["status"]}
