"""Causal feature construction and station-to-river mapping for water quality."""

from __future__ import annotations

from collections import deque
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from hydrolite.gamma_lag_features import build_fast_medium_slow_features
from hydrolite.river_graph import build_graph_from_topology, calculate_topological_order, calculate_upstream_nodes, detect_graph_cycles, validate_river_graph
from hydrolite.trend_aware_features import calculate_robust_local_trend


FEATURE_GROUPS = (
    "local_history", "hydrology", "gamma", "graph_upstream", "trend",
    "seasonal", "meteorology", "flow", "optional_source_context",
)


def map_stations_to_reaches(stations: Any, reaches: Any, *, allow_fallback: bool = True) -> pd.DataFrame:
    station_frame = pd.DataFrame(stations).copy(); reach_frame = pd.DataFrame(reaches).copy()
    if "station_id" not in station_frame:
        raise ValueError("stations require station_id")
    if "reach_id" not in reach_frame:
        raise ValueError("reaches require reach_id")
    valid_reaches = set(reach_frame.reach_id.astype(str))
    rows = []
    for row in station_frame.to_dict(orient="records"):
        station_id = str(row["station_id"]); configured = row.get("reach_id")
        if configured is not None and str(configured) in valid_reaches:
            reach_id, method, confidence, status = str(configured), "configured_exact", "high", "mapped"
        elif allow_fallback and len(valid_reaches) == 1:
            reach_id, method, confidence, status = next(iter(valid_reaches)), "single_reach_fallback", "low", "mapped"
        else:
            reach_id, method, confidence, status = None, "unresolved", "low", "excluded"
        rows.append({"station_id": station_id, "reach_id": reach_id, "mapping_method": method, "mapping_confidence": confidence, "mapping_status": status})
    return pd.DataFrame(rows)


def validate_station_mapping(mapping: Any, reaches: Any) -> dict[str, Any]:
    frame = pd.DataFrame(mapping); valid = set(pd.DataFrame(reaches).reach_id.astype(str))
    missing = sorted({"station_id", "reach_id", "mapping_method", "mapping_confidence", "mapping_status"} - set(frame))
    unresolved = frame.loc[frame.get("mapping_status", pd.Series(index=frame.index, dtype=str)) != "mapped", "station_id"].astype(str).tolist() if not missing else []
    unknown = frame.loc[~frame.get("reach_id", pd.Series(index=frame.index, dtype=str)).astype(str).isin(valid) & frame.get("reach_id", pd.Series(index=frame.index)).notna(), "station_id"].astype(str).tolist() if not missing else []
    return {"status": "passed" if not missing and not unknown else "failed", "missing_columns": missing, "unresolved_stations": unresolved, "unknown_reach_stations": unknown, "mapped_count": int((frame.get("mapping_status") == "mapped").sum()) if not missing else 0}


def build_station_graph(mapping: Any, reach_edges: Any):
    mapped = pd.DataFrame(mapping).query("mapping_status == 'mapped'").copy()
    nodes = pd.DataFrame({"node_id": mapped.station_id.astype(str), "node_type": "water_quality_station"})
    reach_to_station = dict(zip(mapped.reach_id.astype(str), mapped.station_id.astype(str)))
    rows = []
    for index, edge in pd.DataFrame(reach_edges).iterrows():
        source = str(edge.get("source_node", edge.get("upstream_reach_id", "")))
        target = str(edge.get("target_node", edge.get("downstream_reach_id", "")))
        if source in reach_to_station and target in reach_to_station:
            rows.append({"edge_id": str(edge.get("edge_id", f"WQE{index + 1}")), "source_node": reach_to_station[source], "target_node": reach_to_station[target], "edge_type": "upstream_downstream", "distance_km": edge.get("distance_km"), "travel_time": edge.get("travel_time")})
    return build_graph_from_topology(nodes, pd.DataFrame(rows))


def find_upstream_stations(mapping: Any, reach_edges: Any, station_id: str) -> list[str]:
    graph = build_station_graph(mapping, reach_edges)
    if station_id not in {node.node_id for node in graph.nodes}:
        return []
    return calculate_upstream_nodes(graph, str(station_id))


def calculate_network_distance(mapping: Any, reach_edges: Any, upstream_station: str, downstream_station: str) -> dict[str, Any]:
    graph = build_station_graph(mapping, reach_edges)
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.source_node, []).append((edge.target_node, float(edge.distance_km or 1.0)))
    queue = deque([(str(upstream_station), 0.0)])
    visited = set()
    while queue:
        node, distance = queue.popleft()
        if node == str(downstream_station):
            return {"status": "passed", "distance_km": distance, "method": "directed_network_sum"}
        if node in visited: continue
        visited.add(node)
        queue.extend((target, distance + length) for target, length in adjacency.get(node, []))
    return {"status": "unresolved", "distance_km": None, "method": "no_directed_path"}


def build_travel_time_context(mapping: Any, reach_edges: Any, assumed_velocity_kmh: float = 3.0) -> pd.DataFrame:
    graph = build_station_graph(mapping, reach_edges); rows = []
    for edge in graph.edges:
        if edge.travel_time is not None:
            hours, method, confidence = float(edge.travel_time), "configured", "high"
        elif edge.distance_km is not None:
            hours, method, confidence = float(edge.distance_km) / assumed_velocity_kmh, "distance_velocity_fallback", "low"
        else:
            hours, method, confidence = 24.0, "topological_fallback", "low"
        rows.append({"upstream_station_id": edge.source_node, "downstream_station_id": edge.target_node, "travel_time_hours": hours, "method": method, "confidence": confidence})
    return pd.DataFrame(rows)


def build_topological_context(mapping: Any, reach_edges: Any) -> dict[str, Any]:
    graph = build_station_graph(mapping, reach_edges); cycles = detect_graph_cycles(graph)
    return {"status": "passed" if not cycles else "failed", "topological_order": calculate_topological_order(graph) if not cycles else [], "cycles": cycles, "node_count": len(graph.nodes), "edge_count": len(graph.edges), "direction": "upstream_to_downstream"}


def classify_hydrologic_context(data: Any, *, wet_rainfall_mm: float = 1.0, storm_rainfall_mm: float = 10.0, dry_flow_quantile: float = 0.25) -> pd.Series:
    frame = pd.DataFrame(data)
    rain = pd.to_numeric(frame.get("rainfall_mm", 0.0), errors="coerce").fillna(0.0)
    flow = pd.to_numeric(frame.get("flow_cms", np.nan), errors="coerce")
    dry_threshold = float(flow.quantile(dry_flow_quantile)) if flow.notna().any() else np.nan
    context = pd.Series("unknown", index=frame.index, dtype="string")
    context.loc[rain >= storm_rainfall_mm] = "storm_response"
    context.loc[(rain >= wet_rainfall_mm) & (rain < storm_rainfall_mm)] = "wet_weather"
    context.loc[(rain < wet_rainfall_mm) & (flow <= dry_threshold)] = "dry_weather"
    context.loc[(rain < wet_rainfall_mm) & (flow > dry_threshold)] = "recession"
    return context


def build_water_quality_features(observations: Any, flow: Any, hydrology: Any, mapping: Any, reach_edges: Any, meteorology: Any | None = None, *, include_trend: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    obs = pd.DataFrame(observations).copy(); obs["timestamp"] = pd.to_datetime(obs["timestamp"])
    obs = obs[obs.get("training_eligible", True)].sort_values(["station_id", "variable_id", "timestamp"])
    hydro = pd.DataFrame(hydrology).copy(); hydro["timestamp"] = pd.to_datetime(hydro["timestamp"])
    flow_frame = pd.DataFrame(flow).copy(); flow_frame["timestamp"] = pd.to_datetime(flow_frame["timestamp"])
    context = flow_frame.merge(hydro, on=["timestamp", "station_id"], how="outer", suffixes=("", "_hydrology"))
    if meteorology is not None:
        weather = pd.DataFrame(meteorology).copy(); weather["timestamp"] = pd.to_datetime(weather["timestamp"])
        context = context.merge(weather, on=["timestamp", "station_id"], how="left", suffixes=("", "_meteorology"))
    rows = []
    for (station, variable), group in obs.groupby(["station_id", "variable_id"], sort=False):
        group = group.sort_values("timestamp").copy()
        group["local_lag_1"] = group.value.shift(1); group["local_lag_3"] = group.value.shift(3); group["local_lag_7"] = group.value.shift(7)
        group["local_rolling_7"] = group.value.shift(1).rolling(7, min_periods=2).mean()
        group["season_sin"] = np.sin(2 * np.pi * group.timestamp.dt.dayofyear / 365.25)
        group["season_cos"] = np.cos(2 * np.pi * group.timestamp.dt.dayofyear / 365.25)
        if include_trend:
            group["causal_trend_7"] = calculate_robust_local_trend(group.value.shift(1), 7).to_numpy()
        rows.append(group)
    features = pd.concat(rows, ignore_index=True).merge(context, on=["timestamp", "station_id"], how="left", suffixes=("", "_context"))
    rainfall = pd.to_numeric(features.get("rainfall_mm", 0.0), errors="coerce").fillna(0.0)
    gamma_parts = []
    for station, indexes in features.groupby("station_id", sort=False).groups.items():
        ordered = list(features.loc[indexes].sort_values("timestamp").index)
        gamma = build_fast_medium_slow_features(rainfall.loc[ordered].to_numpy())
        gamma.index = ordered; gamma_parts.append(gamma)
    gamma_all = pd.concat(gamma_parts).sort_index().add_prefix("gamma_")
    features = features.join(gamma_all)
    graph = build_station_graph(mapping, reach_edges)
    upstream_map = {node.node_id: calculate_upstream_nodes(graph, node.node_id) for node in graph.nodes}
    lookup = features.set_index(["timestamp", "station_id", "variable_id"])["local_lag_1"]
    def upstream_mean(row: Any) -> float:
        values = np.asarray([lookup.get((row.timestamp, upstream, row.variable_id), np.nan) for upstream in upstream_map.get(str(row.station_id), [])], dtype=float)
        return float(np.mean(values[np.isfinite(values)])) if np.isfinite(values).any() else np.nan
    features["upstream_lag_1_mean"] = [upstream_mean(row) for row in features.itertuples()]
    features["hydrologic_context"] = classify_hydrologic_context(features)
    feature_columns = [column for column in features if column.startswith(("local_", "gamma_", "upstream_", "causal_trend_", "season_"))]
    feature_columns += [column for column in ("flow_cms", "rainfall_mm", "surface_runoff", "interflow", "baseflow", "soil_moisture", "temperature_c", "source_load") if column in features]
    provenance = pd.DataFrame([{
        "feature_name": column,
        "feature_group": ("graph_upstream" if column.startswith("upstream_") else "gamma" if column.startswith("gamma_") else "trend" if column.startswith("causal_trend_") else "seasonal" if column.startswith("season_") else "local_history" if column.startswith("local_") else "flow" if column == "flow_cms" else "hydrology"),
        "source_timestamp_rule": "timestamp <= issue_time",
        "source_direction": "true_upstream_only" if column.startswith("upstream_") else "local",
        "causal": True,
        "transformation": column,
    } for column in feature_columns])
    features.attrs["feature_columns"] = feature_columns
    return features, provenance


def detect_water_quality_feature_leakage(features: Any, provenance: Any, issue_time_column: str = "timestamp") -> dict[str, Any]:
    frame = pd.DataFrame(features); prov = pd.DataFrame(provenance)
    future_columns = [column for column in frame if column.startswith(("future_", "lead_observed_", "downstream_"))]
    noncausal = prov.loc[~prov.get("causal", pd.Series(True, index=prov.index)).astype(bool), "feature_name"].astype(str).tolist() if len(prov) else []
    bad_direction = prov.loc[prov.get("source_direction", pd.Series("local", index=prov.index)).eq("downstream"), "feature_name"].astype(str).tolist() if len(prov) else []
    return {"status": "passed" if not future_columns and not noncausal and not bad_direction else "failed", "future_columns": future_columns, "noncausal_features": noncausal, "downstream_features": bad_direction, "issue_time_column": issue_time_column}


def validate_water_quality_features(features: Any, provenance: Any) -> dict[str, Any]:
    frame = pd.DataFrame(features); required = {"timestamp", "station_id", "variable_id", "value"}; missing = sorted(required - set(frame)); leakage = detect_water_quality_feature_leakage(frame, provenance)
    return {"status": "passed" if not missing and leakage["status"] == "passed" else "failed", "missing_columns": missing, "leakage": leakage, "row_count": len(frame), "feature_count": len(pd.DataFrame(provenance))}


map_water_quality_station_to_graph = map_stations_to_reaches
validate_station_graph_mapping = validate_station_mapping
find_upstream_water_quality_stations = find_upstream_stations
calculate_station_network_distance = calculate_network_distance
calculate_station_travel_time_context = build_travel_time_context
build_station_topological_context = build_topological_context


def align_water_quality_and_weather(observations: Any, weather: Any, tolerance: str = "12h") -> pd.DataFrame:
    left = pd.DataFrame(observations).copy(); right = pd.DataFrame(weather).copy(); left["timestamp"] = pd.to_datetime(left.timestamp); right["timestamp"] = pd.to_datetime(right.timestamp)
    parts = [pd.merge_asof(group.sort_values("timestamp"), right[right.station_id.astype(str) == str(station)].sort_values("timestamp").drop(columns="station_id"), on="timestamp", direction="backward", tolerance=pd.Timedelta(tolerance)) for station, group in left.groupby("station_id", sort=False)]
    result = pd.concat(parts, ignore_index=True); result["alignment_tolerance"] = tolerance; result["future_context_used"] = False; return result


align_upstream_station_observations = align_water_quality_and_weather
align_hydrologic_states = align_water_quality_and_weather


def validate_alignment(data: Any) -> dict[str, Any]:
    frame = pd.DataFrame(data); future = bool(frame.get("future_context_used", pd.Series(False, index=frame.index)).astype(bool).any()); return {"status": "passed" if not future else "failed", "future_context_used": future, "row_count": len(frame)}


def build_upstream_station_features(*args: Any, **kwargs: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    return build_water_quality_features(*args, **kwargs)


def apply_travel_time_shift(data: Any, travel_time_days: int, value_column: str = "value") -> pd.DataFrame:
    frame = pd.DataFrame(data).copy().sort_values("timestamp"); frame[f"{value_column}_travel_shifted"] = frame[value_column].shift(int(travel_time_days)); frame["travel_shift_direction"] = "historical_to_future_target"; return frame


def aggregate_upstream_quality(data: Any, value_column: str = "value") -> float:
    values = pd.to_numeric(pd.DataFrame(data)[value_column], errors="coerce"); return float(values.mean())


def detect_downstream_quality_leakage(provenance: Any) -> dict[str, Any]:
    frame = pd.DataFrame(provenance); leaked = frame.loc[frame.get("source_direction", pd.Series("local", index=frame.index)).eq("downstream"), "feature_name"].astype(str).tolist(); return {"status": "passed" if not leaked else "failed", "downstream_features": leaked}


def validate_upstream_quality_causality(features: Any, provenance: Any) -> dict[str, Any]:
    return detect_water_quality_feature_leakage(features, provenance)
