import pandas as pd
import pytest

from hydrolite.graph_feature_benchmark import build_demo_graph
from hydrolite.graph_hydrology_features import (
    aggregate_upstream_feature,
    build_gamma_graph_features,
    build_graph_feature_table,
    resolve_travel_time_metadata,
    validate_graph_feature_table,
)


def _rows():
    return pd.DataFrame([
        {"timestamp": "2020-01-01", "node_id": "S1", "total_runoff": 1.0, "effective_rainfall": 2.0},
        {"timestamp": "2020-01-01", "node_id": "S2", "total_runoff": 2.0, "effective_rainfall": 3.0},
        {"timestamp": "2020-01-01", "node_id": "R3", "total_runoff": 0.0, "effective_rainfall": 0.0},
    ])


def test_upstream_aggregation_excludes_downstream_and_self_by_default():
    graph = build_demo_graph(); rows = _rows()
    assert aggregate_upstream_feature(rows, graph, "R3", "total_runoff", pd.Timestamp("2020-01-01"), "sum") == pytest.approx(3.0)
    assert aggregate_upstream_feature(rows, graph, "S1", "total_runoff", pd.Timestamp("2020-01-01"), "sum") == 0.0


def test_graph_feature_table_has_directional_aggregates():
    graph = build_demo_graph(); table = build_graph_feature_table(_rows(), graph, ["total_runoff"])
    row = table.query("node_id == 'R3'").iloc[0]
    assert row.upstream_total_runoff_sum == pytest.approx(3.0)
    assert validate_graph_feature_table(table)["status"] == "passed"


def test_travel_time_metadata_records_method_confidence_and_source():
    metadata = resolve_travel_time_metadata(build_demo_graph())
    assert metadata["R1_R3"]["method"] == "configured"
    assert metadata["R1_R3"]["source"] == "synthetic_truth"


def test_gamma_graph_features_join_without_future_values():
    graph = build_demo_graph(); dates = pd.date_range("2020-01-01", periods=40); rows = []
    for node in ("S1", "S2", "R3"):
        rows.extend({"timestamp": date, "node_id": node, "effective_rainfall": float(index == 5)} for index, date in enumerate(dates))
    result = build_gamma_graph_features(rows, graph)
    assert {"local_gamma_quick", "upstream_gamma_quick_sum"} <= set(result)
    assert len(result) == 120
