import pandas as pd
import pytest


def test_rainfall_contract_distinguishes_scenario_and_forecast():
    from hydrolite.forecast_contracts import normalize_rainfall_forecast, validate_rainfall_forecast_frame

    frame = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=3, freq="h"), "rain_mm": [0, 2, 1]})
    normalized = normalize_rainfall_forecast(frame)
    assert validate_rainfall_forecast_frame(normalized)["status"] == "passed"
    assert set(normalized["source"]) == {"scenario"}
    normalized.loc[0, "precipitation_mm"] = -1
    assert validate_rainfall_forecast_frame(normalized)["status"] == "failed"


def test_forecast_horizon_rejects_nonpositive():
    from hydrolite.forecast_contracts import validate_forecast_horizon

    with pytest.raises(ValueError):
        validate_forecast_horizon(0)
