"""Causal feature aggregation on an upstream-to-downstream river graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from hydrolite.gamma_lag_features import build_fast_medium_slow_features
from hydrolite.river_graph import RiverGraph, calculate_graph_depth, calculate_upstream_nodes, calculate_upstream_area, validate_river_graph


FEATURE_COLUMNS = [
    "precipitation", "effective_rainfall", "pet", "aet", "soil_moisture",
    "surface_runoff", "interflow", "baseflow", "total_runoff", "water_yield",
    "total_water_yield", "reach_flow", "reservoir_storage",
]
AGGREGATIONS = {"sum", "mean", "area_weighted", "max", "min", "travel_time_weighted", "distance_decay"}


def build_node_feature_matrix(data: Any, feature_columns: Sequence[str] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(data).copy(); columns = list(feature_columns or FEATURE_COLUMNS)
    for column in columns:
        if column not in frame: frame[column] = 0.0
    identifiers = [column for column in ("timestamp", "node_id") if column in frame]
    return frame[identifiers + columns]


def _upstream_rows(frame: pd.DataFrame, graph: Any, node_id: str, timestamp: Any, include_self: bool = False) -> pd.DataFrame:
    allowed = calculate_upstream_nodes(graph, str(node_id))
    if include_self: allowed.append(str(node_id))
    return frame[(frame["timestamp"] == timestamp) & frame["node_id"].astype(str).isin(allowed)]


def aggregate_upstream_feature(
    features: Any,
    graph: Any,
    node_id: str,
    variable: str,
    timestamp: Any,
    method: str = "sum",
    *,
    include_self: bool = False,
    travel_times: Mapping[str, float] | None = None,
    distances: Mapping[str, float] | None = None,
) -> float:
    if method not in AGGREGATIONS: raise ValueError(f"Unsupported graph aggregation: {method}")
    frame = pd.DataFrame(features).copy(); frame["timestamp"] = pd.to_datetime(frame["timestamp"]); time = pd.Timestamp(timestamp)
    rows = _upstream_rows(frame, graph, str(node_id), time, include_self)
    if rows.empty: return 0.0
    values = pd.to_numeric(rows[variable], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    if method == "sum": return float(values.sum())
    if method == "mean": return float(values.mean())
    if method == "max": return float(values.max())
    if method == "min": return float(values.min())
    if method == "area_weighted":
        areas = calculate_upstream_area(graph); weights = np.asarray([areas.get(str(node), 0.0) for node in rows.node_id], dtype=float)
    elif method == "travel_time_weighted":
        weights = np.exp(-np.asarray([float((travel_times or {}).get(str(node), 0.0)) for node in rows.node_id]))
    else:
        weights = np.exp(-np.asarray([float((distances or {}).get(str(node), 0.0)) for node in rows.node_id]))
    return float(np.average(values, weights=weights)) if weights.sum() else float(values.mean())


def aggregate_travel_time_feature(features: Any, graph: Any, node_id: str, variable: str, timestamp: Any, travel_times: Mapping[str, float]) -> float:
    return aggregate_upstream_feature(features, graph, node_id, variable, timestamp, "travel_time_weighted", travel_times=travel_times)


def aggregate_upstream_features(features: Any, graph: Any) -> pd.DataFrame:
    """Legacy cumulative sum with transitive upstream contributors."""
    frame = pd.DataFrame(features).copy(); frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    numeric = [column for column in frame.select_dtypes(include=[np.number]).columns if column not in {"timestamp"}]
    result = frame.copy()
    for row_index, row in frame.iterrows():
        rows = _upstream_rows(frame, graph, str(row.node_id), row.timestamp)
        if not rows.empty: result.loc[row_index, numeric] = frame.loc[row_index, numeric].to_numpy(dtype=float) + rows[numeric].sum().to_numpy(dtype=float)
    return result


def resolve_travel_time_metadata(graph: Any, assumed_velocity_kmh: float = 5.0) -> dict[str, dict[str, Any]]:
    value = graph if isinstance(graph, RiverGraph) else None
    if value is None:
        from hydrolite.river_graph import _coerce_graph
        value = _coerce_graph(graph)
    result: dict[str, dict[str, Any]] = {}
    for edge in value.edges:
        if edge.travel_time is not None:
            method, travel_time, confidence = str(edge.metadata.get("travel_time_method", "configured")), float(edge.travel_time), "configured" if edge.metadata.get("travel_time_method") in {None, "configured"} else "diagnostic"
        elif edge.distance_km is not None:
            method, travel_time, confidence = "distance_assumed_velocity", float(edge.distance_km) / float(assumed_velocity_kmh), "assumed"
        else:
            method, travel_time, confidence = "topological_fallback", 1.0, "low"
        result[edge.edge_id] = {"source_node": edge.source_node, "target_node": edge.target_node, "travel_time": travel_time, "units": "timestep", "method": method, "parameters": {"assumed_velocity_kmh": assumed_velocity_kmh} if method == "distance_assumed_velocity" else {}, "confidence": confidence, "source": edge.metadata.get("source", "graph_edge")}
    return result


def build_graph_feature_table(features: Any, graph: Any, variables: Sequence[str] | None = None) -> pd.DataFrame:
    validation = validate_river_graph(graph)
    if validation.status != "passed": raise ValueError(f"Invalid river graph: {validation.errors}")
    frame = pd.DataFrame(features).copy(); frame["timestamp"] = pd.to_datetime(frame["timestamp"]); frame["node_id"] = frame.node_id.astype(str)
    variables = list(variables or [column for column in FEATURE_COLUMNS if column in frame])
    depth = calculate_graph_depth(graph); area = calculate_upstream_area(graph); travel = resolve_travel_time_metadata(graph)
    rows = []
    for row in frame.itertuples(index=False):
        base = {"timestamp": row.timestamp, "node_id": str(row.node_id), "graph_depth": depth[str(row.node_id)], "upstream_area_km2": area[str(row.node_id)], "upstream_node_count": len(calculate_upstream_nodes(graph, str(row.node_id)))}
        for variable in variables:
            base[f"local_{variable}"] = float(getattr(row, variable))
            base[f"upstream_{variable}_sum"] = aggregate_upstream_feature(frame, graph, str(row.node_id), variable, row.timestamp, "sum")
            base[f"upstream_{variable}_mean"] = aggregate_upstream_feature(frame, graph, str(row.node_id), variable, row.timestamp, "mean")
        rows.append(base)
    result = pd.DataFrame(rows)
    result.attrs["travel_time_metadata"] = travel
    result.attrs["direction"] = "upstream_to_downstream"
    return result


def build_gamma_graph_features(features: Any, graph: Any, source_variable: str = "effective_rainfall", specs: Mapping[str, Any] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(features).copy(); frame["timestamp"] = pd.to_datetime(frame["timestamp"]); parts = []
    for node_id, group in frame.sort_values("timestamp").groupby("node_id", sort=False):
        gamma = build_fast_medium_slow_features(group[source_variable].to_numpy(dtype=float), specs).add_prefix("gamma_")
        gamma.insert(0, "node_id", str(node_id)); gamma.insert(0, "timestamp", group.timestamp.to_numpy()); parts.append(gamma)
    local = pd.concat(parts, ignore_index=True)
    variables = [column for column in local if column.startswith("gamma_")]
    graph_features = build_graph_feature_table(local, graph, variables)
    graph_features.attrs["feature_group"] = "gamma_graph"
    return graph_features


def build_hydrolite_graph_features(features: Any, graph: Any, variables: Sequence[str] | None = None) -> pd.DataFrame:
    return build_graph_feature_table(features, graph, variables)


def build_feature_matrix(*groups: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged: pd.DataFrame | None = None; provenance = []
    for group_name, data in groups:
        frame = pd.DataFrame(data).copy(); keys = [key for key in ("timestamp", "node_id") if key in frame]
        merged = frame if merged is None else merged.merge(frame, on=keys, how="outer", suffixes=("", f"_{group_name}"))
        for column in frame.columns:
            if column not in keys:
                provenance.append({"feature_name": column, "source_variable": column.removeprefix("local_").split("_")[0], "source_node": "row_node_or_true_upstream", "source_timestamp_range": "at_or_before_issue_time", "transformation": group_name, "parameters": "{}", "training_fit_required": group_name == "seasonal", "causal": True, "feature_group": group_name})
    return (merged if merged is not None else pd.DataFrame()), pd.DataFrame(provenance)


def detect_downstream_leakage(feature_provenance: Any, graph: Any, target_node: str) -> dict[str, Any]:
    allowed = set(calculate_upstream_nodes(graph, str(target_node))) | {str(target_node)}
    frame = pd.DataFrame(feature_provenance); used = set(frame.get("source_node", pd.Series(dtype=str)).dropna().astype(str)) - {"row_node_or_true_upstream"}
    leaked = sorted(used - allowed)
    return {"status": "passed" if not leaked else "downstream_leakage_detected", "target_node": str(target_node), "leaked_nodes": leaked, "allowed_nodes": sorted(allowed)}


def detect_temporal_graph_leakage(feature_provenance: Any, issue_time: Any) -> dict[str, Any]:
    frame = pd.DataFrame(feature_provenance); cutoff = pd.Timestamp(issue_time); leaked = []
    if "source_timestamp" in frame:
        source = pd.to_datetime(frame.source_timestamp, errors="coerce"); leaked = frame.loc[source > cutoff].index.tolist()
    return {"status": "passed" if not leaked else "temporal_graph_leakage_detected", "issue_time": cutoff.isoformat(), "leaked_rows": leaked}


def validate_graph_feature_causality(feature_provenance: Any, graph: Any, target_node: str, issue_time: Any) -> dict[str, Any]:
    downstream = detect_downstream_leakage(feature_provenance, graph, target_node); temporal = detect_temporal_graph_leakage(feature_provenance, issue_time)
    return {"status": "passed" if downstream["status"] == temporal["status"] == "passed" else "failed", "downstream": downstream, "temporal": temporal}


def validate_graph_feature_table(features: Any) -> dict[str, Any]:
    frame = pd.DataFrame(features); missing = sorted({"timestamp", "node_id"} - set(frame)); duplicate = int(frame.duplicated([column for column in ("timestamp", "node_id") if column in frame]).sum()) if not missing else 0
    errors = ([f"missing_columns:{','.join(missing)}"] if missing else []) + (["duplicate_node_timestamp"] if duplicate else [])
    return {"status": "passed" if not errors else "failed", "errors": errors, "row_count": len(frame), "feature_count": max(0, len(frame.columns) - 2)}


def normalize_graph_features(features: Any) -> pd.DataFrame:
    frame = pd.DataFrame(features).copy(); numeric = frame.select_dtypes("number").columns; frame[numeric] = (frame[numeric] - frame[numeric].mean()) / frame[numeric].std().replace(0, 1); return frame


def write_graph_feature_manifest(features: Any, provenance: Any, output_dir: str | Path) -> Path:
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); frame = pd.DataFrame(features); prov = pd.DataFrame(provenance)
    with pd.ExcelWriter(root / "feature_manifest.xlsx") as writer:
        pd.DataFrame([validate_graph_feature_table(frame)]).to_excel(writer, sheet_name="overview", index=False); prov.to_excel(writer, sheet_name="provenance", index=False)
    payload = {**validate_graph_feature_table(frame), "feature_groups": sorted(set(prov.get("feature_group", []))), "direction": "upstream_to_downstream", "travel_time": frame.attrs.get("travel_time_metadata", {})}
    (root / "graph_feature_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return root / "feature_manifest.xlsx"


def write_graph_feature_summary(features: Any, output_dir: str | Path = "output/method_inspiration") -> Path:
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); path = root / "graph_feature_summary.xlsx"; pd.DataFrame(features).describe(include="all").transpose().to_excel(path); return path
