import pandas as pd

from hydrolite.water_quality_features import detect_downstream_quality_leakage, detect_water_quality_feature_leakage


def test_downstream_feature_is_rejected():
    provenance = pd.DataFrame([{"feature_name": "bad", "source_direction": "downstream", "causal": True}])
    assert detect_downstream_quality_leakage(provenance)["status"] == "failed"


def test_future_observation_or_flow_column_is_rejected():
    features = pd.DataFrame({"timestamp": ["2025-01-01"], "future_flow": [1.0], "lead_observed_TN": [1.2]})
    assert detect_water_quality_feature_leakage(features, pd.DataFrame())["status"] == "failed"


def test_causal_local_and_upstream_provenance_passes():
    features = pd.DataFrame({"timestamp": ["2025-01-01"], "local_lag_1": [1.0], "upstream_lag_1": [0.8]})
    provenance = pd.DataFrame([{"feature_name": "local_lag_1", "source_direction": "local", "causal": True}, {"feature_name": "upstream_lag_1", "source_direction": "true_upstream_only", "causal": True}])
    assert detect_water_quality_feature_leakage(features, provenance)["status"] == "passed"
