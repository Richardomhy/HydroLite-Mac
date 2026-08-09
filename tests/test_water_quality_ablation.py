import pandas as pd

from hydrolite.water_quality_forecast import calculate_feature_ablation


def test_ablation_allows_mixed_and_not_demonstrated_results():
    metrics = pd.DataFrame([
        {"variable_id": "TN", "horizon_days": 1, "model_id": "station_local_linear", "split": "test", "RMSE": 1.0},
        {"variable_id": "TN", "horizon_days": 1, "model_id": "local_gamma_linear", "split": "test", "RMSE": 0.8},
        {"variable_id": "TN", "horizon_days": 1, "model_id": "graph_gamma_trend_linear", "split": "test", "RMSE": 1.2},
    ])
    result = calculate_feature_ablation(metrics)
    assert set(result.feature_group_value_added) == {"demonstrated_synthetic", "not_demonstrated"}
    assert result.real_data_value_added.eq("not_tested").all()


def test_trend_is_not_required_candidate():
    metrics = pd.DataFrame([{"variable_id": "TP", "horizon_days": 1, "model_id": "station_local_linear", "split": "test", "RMSE": 1.0}])
    assert len(calculate_feature_ablation(metrics)) == 1
