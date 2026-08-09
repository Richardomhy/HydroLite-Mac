import pandas as pd

from hydrolite.graph_feature_benchmark import build_demo_graph
from hydrolite.graph_hydrology_features import detect_downstream_leakage, detect_temporal_graph_leakage, validate_graph_feature_causality


def test_true_upstream_provenance_passes():
    provenance = pd.DataFrame([{"source_node": "S1", "source_timestamp": "2020-01-01"}, {"source_node": "R5", "source_timestamp": "2020-01-02"}])
    assert validate_graph_feature_causality(provenance, build_demo_graph(), "OUTLET", "2020-01-02")["status"] == "passed"


def test_downstream_source_is_detected():
    provenance = pd.DataFrame([{"source_node": "OUTLET"}])
    assert detect_downstream_leakage(provenance, build_demo_graph(), "S1")["status"] == "downstream_leakage_detected"


def test_future_graph_source_is_detected():
    provenance = pd.DataFrame([{"source_node": "S1", "source_timestamp": "2020-01-03"}])
    assert detect_temporal_graph_leakage(provenance, "2020-01-02")["status"] == "temporal_graph_leakage_detected"
