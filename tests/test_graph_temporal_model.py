from hydrolite.graph_temporal_model import validate_graph_temporal_mode


def test_bidirectional_forecast_is_blocked(): assert validate_graph_temporal_mode("graph_bidirectional_hindcast_only", "forecast")["status"] == "future_context_leakage_blocked"
