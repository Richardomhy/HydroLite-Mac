from __future__ import annotations

from pathlib import Path
import pandas as pd

from hydrolite.river_graph import calculate_topological_order

FEATURE_COLUMNS = ["precipitation", "pet", "aet", "soil_moisture", "surface_runoff", "interflow", "baseflow", "total_water_yield", "reach_flow", "reservoir_storage"]


def build_node_feature_matrix(data, feature_columns=None):
    frame = pd.DataFrame(data).copy(); cols = feature_columns or FEATURE_COLUMNS
    missing = [column for column in cols if column not in frame]
    for column in missing: frame[column] = 0.0
    return frame[[column for column in ["timestamp", "node_id"] if column in frame] + cols]


def aggregate_upstream_features(features, graph):
    frame = pd.DataFrame(features).copy(); order = calculate_topological_order(graph); parents = {node: [] for node in graph["nodes"]}
    for up, down in graph["edges"]: parents[down].append(up)
    numeric = [column for column in frame if column not in {"timestamp", "node_id"}]
    for timestamp, group_index in frame.groupby("timestamp").groups.items():
        subset = frame.loc[group_index].set_index("node_id")
        for node in order:
            if node in subset.index and parents[node]:
                upstream = subset.loc[[item for item in parents[node] if item in subset.index], numeric].sum()
                frame.loc[(frame.timestamp == timestamp) & (frame.node_id == node), numeric] += upstream.to_numpy()
    return frame


def normalize_graph_features(features):
    frame = pd.DataFrame(features).copy(); numeric = frame.select_dtypes("number").columns; frame[numeric] = (frame[numeric] - frame[numeric].mean()) / frame[numeric].std().replace(0, 1); return frame


def write_graph_feature_summary(features, output_dir="output/method_inspiration"):
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True); summary = pd.DataFrame(features).describe(include="all").transpose(); summary.to_excel(root / "graph_feature_summary.xlsx"); return root / "graph_feature_summary.xlsx"
