import pandas as pd

from hydrolite.water_quality_forecast import build_forecast_samples, select_water_quality_model_on_validation, validate_forecast_result


def _features():
    dates = pd.date_range("2024-01-01", periods=40)
    return pd.DataFrame({"timestamp": dates, "station_id": "WQ1", "variable_id": "TN", "value": range(40), "local_lag_1": pd.Series(range(40)).shift(1), "flow_cms": 1.0})


def test_forecast_samples_have_required_independent_horizons():
    samples = build_forecast_samples(_features())
    assert set(samples.horizon_days) == {1, 3, 7, 14}
    assert samples.loc[samples.horizon_days == 14, "horizon_status"].eq("long_horizon_diagnostic").all()


def test_model_selection_uses_validation_only_and_is_pollutant_specific():
    metrics = pd.DataFrame([
        {"variable_id": "TN", "horizon_days": 1, "model_id": "a", "split": "validation", "RMSE": 2.0, "MAE": 1.0},
        {"variable_id": "TN", "horizon_days": 1, "model_id": "b", "split": "validation", "RMSE": 1.0, "MAE": 1.0},
        {"variable_id": "TN", "horizon_days": 1, "model_id": "a", "split": "test", "RMSE": 0.0, "MAE": 0.0},
    ])
    selected = select_water_quality_model_on_validation(metrics)
    assert selected.iloc[0].selected_model == "b"
    assert not selected.iloc[0].test_used


def test_forecast_validation_blocks_test_selection_leakage():
    predictions = pd.DataFrame({"timestamp": pd.to_datetime(["2025-01-01"] * 4), "valid_time": pd.to_datetime(["2025-01-02", "2025-01-04", "2025-01-08", "2025-01-15"]), "horizon_days": [1, 3, 7, 14], "predicted": [1, 1, 1, 1]})
    selection = pd.DataFrame({"test_used_for_selection": [True]})
    assert validate_forecast_result(predictions, selection)["status"] == "failed"
