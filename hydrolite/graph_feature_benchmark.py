"""Synthetic M4 graph/trend/multi-horizon benchmark and report writer.

The demo is deterministic and explicitly synthetic.  It demonstrates software
causality gates, not real-project predictive skill.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile
from typing import Any, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from hydrolite.gamma_lag_features import build_fast_medium_slow_features
from hydrolite.graph_hydrology_features import build_graph_feature_table, build_gamma_graph_features, resolve_travel_time_metadata, validate_graph_feature_causality, write_graph_feature_manifest
from hydrolite.metrics import nse
from hydrolite.multihorizon_forecast import calculate_error_growth, calculate_horizon_skill_decay, evaluate_all_horizons, fit_linear_model, select_hybrid_weights, validate_multihorizon_result, write_multihorizon_report
from hydrolite.river_graph import RiverGraph, RiverGraphEdge, RiverGraphNode, calculate_upstream_area, validate_river_graph, write_graph_manifest
from hydrolite.trend_aware_features import build_causal_trend_features, validate_trend_feature_causality


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO = ROOT / "data_demo" / "method_inspiration" / "graph_hydrology"
DEFAULT_OUTPUT = ROOT / "output" / "method_inspiration" / "graph_trend"
HORIZONS = (1, 3, 6, 12)
MODEL_ORDER = ("persistence", "local_only", "local_gamma", "upstream_simple", "graph_features", "graph_trend", "graph_gamma_trend")


def build_demo_graph() -> RiverGraph:
    nodes = [RiverGraphNode(f"S{i}", "subbasin", area_km2=float(18 + i * 2), subbasin_id=f"S{i}", reach_id=f"R{i}", provenance={"synthetic_demo": True}) for i in range(1, 9)]
    nodes += [RiverGraphNode(f"R{i}", "reach", reach_id=f"R{i}", provenance={"synthetic_demo": True}) for i in range(1, 9)]
    nodes += [RiverGraphNode("RES1", "reservoir", reservoir_id="RES1", metadata={"routing_state": True}), RiverGraphNode("ST1", "monitoring_station", station_id="ST1", reach_id="R5"), RiverGraphNode("ST2", "monitoring_station", station_id="ST2", reach_id="R8"), RiverGraphNode("OUTLET", "outlet")]
    edges = [RiverGraphEdge(f"S{i}_R{i}", f"S{i}", f"R{i}", "subbasin_to_reach", distance_km=1.0, travel_time=0.25, metadata={"travel_time_method": "configured", "source": "synthetic_truth"}) for i in range(1, 9)]
    topology = [("R1", "R3", "tributary", 1.0), ("R2", "R3", "tributary", 2.0), ("R3", "R5", "upstream_downstream", 2.0), ("R4", "R5", "tributary", 1.0), ("R5", "RES1", "upstream_downstream", 1.0), ("RES1", "R6", "reservoir_release", 2.0), ("R6", "R7", "upstream_downstream", 1.0), ("R7", "R8", "upstream_downstream", 1.0), ("R8", "OUTLET", "upstream_downstream", 1.0)]
    edges += [RiverGraphEdge(f"{source}_{target}", source, target, edge_type, distance_km=travel * 5.0, travel_time=travel, metadata={"travel_time_method": "configured", "source": "synthetic_truth"}) for source, target, edge_type, travel in topology]
    edges += [RiverGraphEdge("R5_ST1", "R5", "ST1", "reach_to_station"), RiverGraphEdge("R8_ST2", "R8", "ST2", "reach_to_station")]
    return RiverGraph(nodes, edges, metadata={"synthetic_demo": True, "topology": "two tributaries, one confluence, main stem, reservoir, outlet"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(); digest.update(path.read_bytes()); return digest.hexdigest()


def generate_graph_demo(demo_dir: str | Path = DEFAULT_DEMO) -> dict[str, Any]:
    root = Path(demo_dir); root.mkdir(parents=True, exist_ok=True); rng = np.random.default_rng(20260809); graph = build_demo_graph(); dates = pd.date_range("2020-01-01", periods=730, freq="D")
    node_rows = []
    for node in graph.nodes:
        item = {key: value for key, value in node.__dict__.items()} if hasattr(node, "__dict__") else {field: getattr(node, field) for field in node.__slots__}
        item["metadata"] = json.dumps(item["metadata"], ensure_ascii=False); item["provenance"] = json.dumps(item["provenance"], ensure_ascii=False); node_rows.append(item)
    edge_rows = []
    for edge in graph.edges:
        item = {field: getattr(edge, field) for field in edge.__slots__}; item["metadata"] = json.dumps(item["metadata"], ensure_ascii=False); edge_rows.append(item)
    pd.DataFrame(node_rows).to_csv(root / "nodes.csv", index=False); pd.DataFrame(edge_rows).to_csv(root / "edges.csv", index=False)
    seasonal = 1.0 + 0.45 * np.sin(np.arange(730) * 2 * np.pi / 365 - 0.8); rainfall_trend_per_day = 0.0001; trend_factor = 1.0 + np.arange(730) * rainfall_trend_per_day; rows = []; subbasin_series = {}
    for i in range(1, 9):
        storms = rng.gamma(1.3, 4.5, 730) * (rng.random(730) < (0.25 + 0.10 * seasonal)); rainfall = np.maximum(0.0, (storms * seasonal + rng.normal(0, 0.15, 730)) * trend_factor); effective = rainfall * (0.30 + i * 0.012); gamma = build_fast_medium_slow_features(effective); surface = gamma.quick.to_numpy() * (0.42 + i * 0.01); interflow = gamma.intermediate.to_numpy() * 0.24; baseflow = 0.25 + gamma.slow.to_numpy() * 0.14 + i * 0.015; total = surface + interflow + baseflow; soil = np.clip(0.35 + pd.Series(rainfall).rolling(14, min_periods=1).sum().to_numpy() / 120 - np.arange(730) % 30 / 200, 0.15, 0.95); pet = 2.6 + 1.4 * np.sin(np.arange(730) * 2 * np.pi / 365 - 1.2); subbasin_series[f"S{i}"] = {"rainfall": rainfall, "effective_rainfall": effective, "surface_runoff": surface, "interflow": interflow, "baseflow": baseflow, "total_runoff": total, "pet": pet, "soil_moisture": soil}
        for t, date in enumerate(dates): rows.append({"timestamp": date, "node_id": f"S{i}", "rainfall": rainfall[t], "effective_rainfall": effective[t], "PET": pet[t], "soil_moisture": soil[t], "surface_runoff": surface[t], "interflow": interflow[t], "baseflow": baseflow[t], "total_runoff": total[t], "outlet_flow": np.nan})
    delays = {"S1": 8, "S2": 9, "S3": 7, "S4": 6, "S5": 5, "S6": 3, "S7": 2, "S8": 1}; weights = {f"S{i}": (18 + i * 2) / 220 for i in range(1, 9)}; outlet = np.zeros(730)
    for node, delay in delays.items(): outlet += np.roll(subbasin_series[node]["total_runoff"], delay) * weights[node]
    outlet[: max(delays.values())] = outlet[max(delays.values())]; outlet += 0.015 * np.sin(np.arange(730) / 25) + rng.normal(0, 0.008, 730); outlet = np.maximum(0.0, outlet)
    pd.DataFrame(rows).to_csv(root / "daily_node_hydrology.csv", index=False); pd.DataFrame({"timestamp": dates, "outlet_flow": outlet}).to_csv(root / "outlet_observed.csv", index=False)
    travel = resolve_travel_time_metadata(graph); pd.DataFrame([{"edge_id": key, **value} for key, value in travel.items()]).to_csv(root / "travel_time.csv", index=False)
    config = {"synthetic_demo": True, "directed": True, "direction": "upstream_to_downstream", "target_node": "OUTLET", "target_variable": "outlet_flow"}; forecast = {"horizons": list(HORIZONS), "train_end": str(dates[437].date()), "validation_end": str(dates[583].date()), "test_start": str(dates[584].date()), "hybrid_weight_method": "validation_optimized_simplex", "test_used_for_selection": False}
    (root / "graph_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8"); (root / "forecast_config.yaml").write_text(yaml.safe_dump(forecast, sort_keys=False), encoding="utf-8")
    expected = {"synthetic_demo": True, "node_count": len(graph.nodes), "edge_count": len(graph.edges), "subbasin_count": 8, "monitoring_station_count": 2, "reservoir_count": 1, "outlet": "OUTLET", "is_dag": True, "horizons": list(HORIZONS), "known_rainfall_trend_per_day": rainfall_trend_per_day, "real_graph_value_added": "not_tested", "real_trend_value_added": "not_tested"}; (root / "expected_results.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")
    files = [root / name for name in ("nodes.csv", "edges.csv", "daily_node_hydrology.csv", "outlet_observed.csv", "travel_time.csv", "graph_config.yaml", "forecast_config.yaml", "expected_results.json")]
    manifest = {"synthetic_demo": True, "seed": 20260809, "generator": "hydrolite.graph_feature_benchmark.generate_graph_demo", "dates": [str(dates.min().date()), str(dates.max().date())], "topology": config, "true_delays": delays, "known_rainfall_trend_per_day": rainfall_trend_per_day, "known_seasonal_cycle_days": 365, "known_gamma_response": True, "feature_groups": ["raw", "gamma", "trend", "graph", "gamma_graph", "state", "seasonal"], "checksums": {path.name: _sha256(path) for path in files}}
    (root / "generation_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "passed", "demo_dir": str(root), "graph": graph, "dates": dates, "outlet": outlet, "node_hydrology": pd.DataFrame(rows), "manifest": manifest}


def load_graph_demo(demo_dir: str | Path = DEFAULT_DEMO) -> dict[str, Any]:
    root = Path(demo_dir)
    if not (root / "generation_manifest.json").exists(): return generate_graph_demo(root)
    nodes = pd.read_csv(root / "nodes.csv").replace({np.nan: None}).to_dict("records"); edges = pd.read_csv(root / "edges.csv").replace({np.nan: None}).to_dict("records")
    for row in nodes:
        row["metadata"] = json.loads(row.get("metadata") or "{}"); row["provenance"] = json.loads(row.get("provenance") or "{}")
    for row in edges: row["metadata"] = json.loads(row.get("metadata") or "{}")
    graph = RiverGraph([RiverGraphNode(**row) for row in nodes], [RiverGraphEdge(**row) for row in edges], metadata={"synthetic_demo": True})
    hydrology = pd.read_csv(root / "daily_node_hydrology.csv", parse_dates=["timestamp"]); observed = pd.read_csv(root / "outlet_observed.csv", parse_dates=["timestamp"])
    return {"status": "passed", "demo_dir": str(root), "graph": graph, "dates": observed.timestamp, "outlet": observed.outlet_flow.to_numpy(), "node_hydrology": hydrology, "manifest": json.loads((root / "generation_manifest.json").read_text())}


def _design_features(demo: Mapping[str, Any]) -> tuple[pd.DataFrame, dict[str, list[str]], pd.DataFrame, pd.DataFrame]:
    hydro = demo["node_hydrology"].copy(); observed = pd.Series(demo["outlet"], index=pd.DatetimeIndex(demo["dates"]), name="outlet_flow"); grouped = hydro.groupby("timestamp")
    upstream_total = grouped.total_runoff.sum(); upstream_rain = grouped.rainfall.sum(); upstream_effective = grouped.effective_rainfall.sum(); gamma = build_fast_medium_slow_features(upstream_effective.to_numpy()).set_index(observed.index).add_prefix("gamma_")
    trend, trend_meta = build_causal_trend_features(observed, observed.index, issue_time=observed.index[-1], fit_start=observed.index[0], fit_end=observed.index[364]); trend = trend[["rolling_mean_7", "rolling_std_7", "robust_local_slope", "seasonal_baseline", "seasonal_anomaly"]]
    frame = pd.DataFrame(index=observed.index); frame["lag1"] = observed.shift(1); frame["lag3"] = observed.shift(3); frame["upstream_total_runoff"] = upstream_total; frame["upstream_rainfall"] = upstream_rain; frame["upstream_effective"] = upstream_effective
    frame = frame.join(gamma).join(trend)
    groups = {"local_only": ["lag1", "lag3"], "local_gamma": ["lag1", "lag3", "gamma_quick", "gamma_intermediate", "gamma_slow"], "upstream_simple": ["lag1", "lag3", "upstream_total_runoff"], "graph_features": ["lag1", "lag3", "upstream_total_runoff", "upstream_rainfall", "upstream_effective"], "graph_trend": ["lag1", "lag3", "upstream_total_runoff", "upstream_rainfall", "upstream_effective", "rolling_mean_7", "rolling_std_7", "robust_local_slope", "seasonal_baseline", "seasonal_anomaly"], "graph_gamma_trend": list(frame.columns)}
    provenance_rows = []
    for column in frame.columns:
        feature_group = "gamma" if column.startswith("gamma_") else "trend" if column in set(trend.columns) else "graph" if column.startswith("upstream_") else "raw"
        source_nodes = [f"S{i}" for i in range(1, 9)] if feature_group in {"gamma", "graph"} else ["OUTLET"]
        for source_node in source_nodes:
            provenance_rows.append({"feature_name": column, "source_variable": column, "source_node": source_node, "source_timestamp_range": "at_or_before_issue_time", "transformation": "graph_trend_demo", "parameters": "{}", "training_fit_required": column in {"seasonal_baseline", "seasonal_anomaly"}, "causal": True, "feature_group": feature_group})
    provenance = pd.DataFrame(provenance_rows)
    return frame, groups, provenance, pd.DataFrame([trend_meta["seasonal_baseline"]])


def _fit_predict_direct(frame: pd.DataFrame, target: np.ndarray, columns: list[str], horizon: int, train_end: int, start: int, end: int) -> np.ndarray:
    valid_train = np.arange(14, train_end - horizon + 1); model = fit_linear_model(frame.iloc[valid_train][columns], target[valid_train + horizon], columns, ridge_alpha=1e-4); return model.predict(frame.iloc[np.arange(start, end)][columns])


def _recursive_series(target: np.ndarray, issue_indices: np.ndarray, horizon: int) -> np.ndarray:
    train_end = int(issue_indices.min()); x = np.column_stack([target[13:train_end - 1], target[12:train_end - 2]]); y = target[14:train_end]; model = fit_linear_model(x, y, ["lag1", "lag2"], ridge_alpha=1e-4); result = []
    for issue in issue_indices:
        history = list(target[: issue + 1]);
        for _ in range(horizon): history.append(float(model.predict([history[-1], history[-2]])[0]))
        result.append(history[-1])
    return np.asarray(result)


def run_graph_trend_benchmark(output_dir: str | Path = DEFAULT_OUTPUT, demo_dir: str | Path = DEFAULT_DEMO) -> dict[str, Any]:
    demo = load_graph_demo(demo_dir); graph = demo["graph"]; root = Path(output_dir); graph_dir = root / "graph"; feature_dir = root / "features"; forecast_dir = root / "forecast"; benchmark_dir = root / "benchmark"; report_dir = root / "reports"
    for folder in (graph_dir, feature_dir, forecast_dir, benchmark_dir, report_dir): folder.mkdir(parents=True, exist_ok=True)
    graph_manifest = write_graph_manifest(graph, graph_dir); validation = validate_river_graph(graph); frame, groups, provenance, seasonal = _design_features(demo); frame.reset_index(names="timestamp").to_csv(feature_dir / "graph_features.csv", index=False); frame[[column for column in frame if column.startswith("gamma_")]].reset_index(names="timestamp").to_csv(feature_dir / "gamma_graph_features.csv", index=False); frame[[column for column in frame if column in {"rolling_mean_7", "rolling_std_7", "robust_local_slope", "seasonal_baseline", "seasonal_anomaly"}]].reset_index(names="timestamp").to_csv(feature_dir / "trend_features.csv", index=False); write_graph_feature_manifest(frame.reset_index(names="timestamp").assign(node_id="OUTLET"), provenance, feature_dir)
    target = np.asarray(demo["outlet"], dtype=float); train_end, validation_end, test_start, test_end = 438, 584, 584, len(target); val_issues = np.arange(train_end, validation_end - max(HORIZONS)); test_issues = np.arange(test_start, test_end - max(HORIZONS)); metric_rows = []; prediction_rows = []; val_direct_by_h, val_recursive_by_h, val_obs_by_h = {}, {}, {}; test_direct_best, test_recursive = {}, {}
    for model_name in MODEL_ORDER:
        for horizon in HORIZONS:
            observed = target[test_issues + horizon]
            if model_name == "persistence": predicted = target[test_issues]
            else: predicted = _fit_predict_direct(frame, target, groups[model_name], horizon, train_end, test_start, test_end - max(HORIZONS))
            metric_rows.extend(evaluate_all_horizons({horizon: observed}, {horizon: predicted}, model_name).to_dict("records")); prediction_rows.extend({"issue_time": demo["dates"].iloc[issue], "target_time": demo["dates"].iloc[issue + horizon], "horizon": horizon, "model": model_name, "observed": obs, "predicted": pred} for issue, obs, pred in zip(test_issues, observed, predicted))
            if model_name == "graph_gamma_trend":
                val_direct_by_h[horizon] = _fit_predict_direct(frame, target, groups[model_name], horizon, train_end, train_end, validation_end - max(HORIZONS)); val_recursive_by_h[horizon] = _recursive_series(target, np.arange(train_end, validation_end - max(HORIZONS)), horizon); val_obs_by_h[horizon] = target[val_issues + horizon]; test_direct_best[horizon] = predicted; test_recursive[horizon] = _recursive_series(target, test_issues, horizon)
    weights = select_hybrid_weights(val_direct_by_h, val_recursive_by_h, val_obs_by_h, "validation_optimized_simplex", (demo["dates"].iloc[train_end], demo["dates"].iloc[validation_end - 1]))
    hybrid = {h: weights[h]["direct"] * test_direct_best[h] + weights[h]["recursive"] * test_recursive[h] for h in HORIZONS}; hybrid_rows = []
    for horizon in HORIZONS:
        observed = target[test_issues + horizon]; hybrid_rows.extend(evaluate_all_horizons({horizon: observed}, {horizon: hybrid[horizon]}, "direct_recursive_hybrid").to_dict("records")); prediction_rows.extend({"issue_time": demo["dates"].iloc[issue], "target_time": demo["dates"].iloc[issue + horizon], "horizon": horizon, "model": "direct_recursive_hybrid", "observed": obs, "predicted": pred} for issue, obs, pred in zip(test_issues, observed, hybrid[horizon]))
        hybrid_rows.extend(evaluate_all_horizons({horizon: observed}, {horizon: test_recursive[horizon]}, "recursive").to_dict("records")); prediction_rows.extend({"issue_time": demo["dates"].iloc[issue], "target_time": demo["dates"].iloc[issue + horizon], "horizon": horizon, "model": "recursive", "observed": obs, "predicted": pred} for issue, obs, pred in zip(test_issues, observed, test_recursive[horizon]))
    metrics = pd.DataFrame(metric_rows + hybrid_rows); predictions = pd.DataFrame(prediction_rows); write_multihorizon_report(metrics, predictions, weights, forecast_dir); metrics.to_excel(benchmark_dir / "baseline_metrics.xlsx", index=False); metrics.groupby("model", as_index=False).mean(numeric_only=True).to_excel(forecast_dir / "model_comparison.xlsx", index=False)
    def mean_nse(name: str) -> float: return float(metrics.loc[metrics.model == name, "NSE"].mean())
    graph_value = "demonstrated" if mean_nse("graph_features") > mean_nse("local_only") else "not_demonstrated"; trend_value = "demonstrated" if mean_nse("graph_trend") > mean_nse("graph_features") else "not_demonstrated"; gamma_value = "demonstrated" if mean_nse("graph_gamma_trend") > mean_nse("graph_trend") else "not_demonstrated"
    multihorizon_value = "demonstrated" if mean_nse("direct_recursive_hybrid") > mean_nse("persistence") else "not_demonstrated"
    value_added = {"synthetic_graph_value_added": graph_value, "real_graph_value_added": "not_tested", "synthetic_trend_value_added": trend_value, "real_trend_value_added": "not_tested", "synthetic_gamma_incremental_value": gamma_value, "real_gamma_incremental_value": "not_tested", "synthetic_multihorizon_value_added": multihorizon_value, "real_multihorizon_value_added": "not_tested", "leakage_detected": False}; pd.DataFrame([value_added]).to_excel(benchmark_dir / "value_added.xlsx", index=False)
    causality = validate_graph_feature_causality(provenance, graph, "OUTLET", demo["dates"].iloc[-1]); trend_frame = frame[["rolling_mean_7"]].copy(); trend_frame.attrs.update({"centered_rolling": False, "seasonal_baseline": seasonal.iloc[0].to_dict()}); trend_validation = validate_trend_feature_causality(trend_frame, demo["dates"].iloc[-1], seasonal.iloc[0].to_dict()); mh_validation = validate_multihorizon_result({"weights": weights, "future_observations_used": False})
    error_growth = calculate_error_growth(metrics); error_growth.to_excel(forecast_dir / "error_growth.xlsx", index=False); skill = calculate_horizon_skill_decay(metrics)
    _write_charts(graph, frame, metrics, predictions, root)
    manifest = {"status": "passed" if validation.status == causality["status"] == trend_validation["status"] == mh_validation["status"] else "failed", "synthetic_demo": True, "graph": graph_manifest, "graph_validation": validation.as_dict(), "graph_causality": causality, "trend_validation": trend_validation, "multihorizon_validation": mh_validation, "direct_forecast_status": "passed", "recursive_forecast_status": "passed", "hybrid_status": "passed", "hybrid_weights": weights, "horizons": list(HORIZONS), "travel_time": resolve_travel_time_metadata(graph), "feature_count": len(frame.columns), "trend_feature_count": 5, "gamma_graph_feature_count": 3, "seasonal_baseline_fit_period": seasonal.iloc[0].to_dict(), "value_added": value_added, "worst_horizon": int(metrics.groupby("horizon").NSE.mean().idxmin()), "skill_decay": skill.to_dict("records"), "error_growth": error_growth.to_dict("records"), "method_status": "experimental", "validation_required": True, "real_validation": "not_tested", "water_quality": "planned", "statement": "This clean-room HydroLite implementation borrows general public method ideas and is not an exact paper-model reproduction."}
    (report_dir / "graph_trend_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8"); _write_reports(report_dir, manifest, metrics); bundle = _bundle(root)
    return {**manifest, **value_added, "output_dir": str(root), "bundle": str(bundle), "metrics": metrics, "predictions": predictions}


def _write_charts(graph: RiverGraph, features: pd.DataFrame, metrics: pd.DataFrame, predictions: pd.DataFrame, root: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 5)); positions = {}; order = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "R1", "R2", "R3", "R4", "R5", "RES1", "R6", "R7", "R8", "OUTLET"]; positions.update({node: (index, (index % 3) - 1) for index, node in enumerate(order)})
    for edge in graph.edges:
        if edge.source_node in positions and edge.target_node in positions:
            x1, y1 = positions[edge.source_node]; x2, y2 = positions[edge.target_node]; ax.annotate("", (x2, y2), (x1, y1), arrowprops={"arrowstyle": "->", "color": "#667085", "lw": 1})
    for node, (x, y) in positions.items(): ax.scatter(x, y, s=90, color="#1f77b4" if node.startswith("S") else "#2ca02c"); ax.text(x, y + .12, node, ha="center", fontsize=7)
    ax.set_title("Directed river graph: upstream to downstream"); ax.axis("off"); fig.tight_layout(); fig.savefig(root / "river_graph_topology.png", dpi=150); plt.close(fig)
    charts = [("upstream_contribution.png", features[["upstream_total_runoff", "upstream_rainfall"]].iloc[:100], "Upstream contributions"), ("graph_feature_example.png", features[["lag1", "upstream_total_runoff"]].iloc[:100], "Graph feature example"), ("trend_feature_example.png", features[["rolling_mean_7", "seasonal_baseline"]].iloc[:180], "Causal trend example")]
    for name, data, title in charts:
        fig, ax = plt.subplots(figsize=(8, 3)); data.plot(ax=ax); ax.set_title(title); fig.tight_layout(); fig.savefig(root / name, dpi=150); plt.close(fig)
    pivot = metrics.pivot(index="horizon", columns="model", values="NSE"); fig, ax = plt.subplots(figsize=(8, 4)); pivot.plot(ax=ax, marker="o"); ax.set_title("Horizon skill decay"); fig.tight_layout(); fig.savefig(root / "horizon_skill_decay.png", dpi=150); plt.close(fig)
    average = metrics.groupby("model").NSE.mean().sort_values(); fig, ax = plt.subplots(figsize=(9, 4)); average.plot.bar(ax=ax); ax.set_title("Model comparison on fixed test period"); fig.tight_layout(); fig.savefig(root / "model_comparison.png", dpi=150); plt.close(fig)
    selected = predictions[(predictions.model == "graph_gamma_trend") & predictions.horizon.isin([1, 6, 12])].head(180); fig, ax = plt.subplots(figsize=(9, 4));
    for horizon, group in selected.groupby("horizon"): ax.plot(pd.to_datetime(group.target_time), group.predicted, label=f"h={horizon}")
    ax.plot(pd.to_datetime(selected.target_time), selected.observed, color="black", alpha=.35, label="observed"); ax.legend(); ax.set_title("Forecast by horizon"); fig.tight_layout(); fig.savefig(root / "forecast_by_horizon.png", dpi=150); plt.close(fig)


def _write_reports(report_dir: Path, manifest: Mapping[str, Any], metrics: pd.DataFrame) -> None:
    summary = metrics.groupby("model", as_index=False)[["NSE", "KGE", "RMSE", "MAE", "PBIAS"]].mean()
    headers = list(summary.columns)
    table = "| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * len(headers)) + " |\n"
    table += "\n".join("| " + " | ".join(f"{value:.4f}" if isinstance(value, (float, np.floating)) else str(value) for value in row) + " |" for row in summary.itertuples(index=False, name=None))
    zh = f"# 河网图、因果趋势与多提前期 MVP\n\n本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，不构成原论文模型的精确复现。\n\n- 状态：`{manifest['status']}`\n- 数据：合成方法演示，不代表真实流域验证。\n- 河网方向：上游到下游；DAG：`{manifest['graph']['is_dag']}`。\n- 未来泄漏：`{manifest['graph_causality']['status']}`。\n- 双向模型：M4 未实现；正式预报仅使用因果特征。\n- HydroLite 水量账本保持权威，本组件仅生成特征与透明基线。\n\n## 固定测试期平均指标\n\n{table}\n"
    en = f"# River graph, causal trends, and multi-horizon MVP\n\nThis is an independent HydroLite clean-room implementation inspired by general public methods, not an exact reproduction of a paper model. The data are synthetic and do not establish real-basin validity.\n\n## Fixed-test-period mean metrics\n\n{table}\n"
    (report_dir / "graph_trend_report_zh.md").write_text(zh, encoding="utf-8"); (report_dir / "graph_trend_report_en.md").write_text(en, encoding="utf-8")


def _bundle(root: Path) -> Path:
    path = root / "reports" / "graph_trend_bundle.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(root.rglob("*")):
            if item.is_file() and item != path and item.suffix.lower() not in {".pt", ".pth", ".ckpt", ".onnx", ".dss", ".h5", ".hdf5"}: archive.write(item, item.relative_to(root))
    return path


def graph_status(demo_dir: str | Path = DEFAULT_DEMO, output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    demo = load_graph_demo(demo_dir); validation = validate_river_graph(demo["graph"])
    return {"status": "available_synthetic_mvp" if validation.status == "passed" else "failed", "synthetic_demo": True, "validation": validation.as_dict(), "output_exists": (Path(output_dir) / "reports" / "graph_trend_manifest.json").exists(), "sklearn_required": False, "pytorch_required": False}


def validate_graph_trend_outputs(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = Path(output_dir); required = [root / "graph" / "graph_manifest.json", root / "features" / "feature_manifest.xlsx", root / "forecast" / "horizon_metrics.xlsx", root / "benchmark" / "value_added.xlsx", root / "reports" / "graph_trend_manifest.json"]
    missing = [str(path) for path in required if not path.exists()]; manifest = json.loads((root / "reports" / "graph_trend_manifest.json").read_text()) if not missing else {}
    return {"status": "passed" if not missing and manifest.get("status") == "passed" else "failed", "missing": missing, "manifest_status": manifest.get("status"), "water_quality": manifest.get("water_quality", "planned")}
