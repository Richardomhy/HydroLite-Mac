import pandas as pd

from hydrolite.water_quality_features import FEATURE_GROUPS, apply_travel_time_shift, classify_hydrologic_context, validate_water_quality_features


def test_feature_groups_include_reused_gamma_graph_and_optional_trend():
    assert {"gamma", "graph_upstream", "trend", "hydrology", "flow"}.issubset(FEATURE_GROUPS)


def test_travel_time_shift_uses_history_only():
    shifted = apply_travel_time_shift(pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=3), "value": [1, 2, 3]}), 1)
    assert pd.isna(shifted.iloc[0].value_travel_shifted)
    assert shifted.iloc[1].value_travel_shifted == 1


def test_hydrologic_context_is_diagnostic_not_source_identification():
    contexts = classify_hydrologic_context(pd.DataFrame({"rainfall_mm": [0, 2, 20], "flow_cms": [1, 2, 5]}))
    assert set(contexts).issubset({"dry_weather", "wet_weather", "storm_response", "recession", "unknown"})
