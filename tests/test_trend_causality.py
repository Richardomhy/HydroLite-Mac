import numpy as np
import pandas as pd
import pytest

from hydrolite.trend_aware_features import build_causal_trend_features, build_rolling_features, validate_trend_feature_causality


def test_centered_rolling_is_blocked_for_forecast():
    with pytest.raises(ValueError, match="centered_rolling_forecast_blocked"):
        build_rolling_features(range(10), centered=True)
    assert build_rolling_features(range(10), centered=True, analysis_only=True).attrs["analysis_only"] is True


def test_future_perturbation_does_not_change_past_features():
    dates = pd.date_range("2020-01-01", periods=80); values = np.arange(80.0); cutoff = dates[50]
    first, meta = build_causal_trend_features(values, dates, issue_time=cutoff, fit_end=dates[30]); changed = values.copy(); changed[51:] += 10000
    second, _ = build_causal_trend_features(changed, dates, issue_time=cutoff, fit_end=dates[30])
    assert np.nanmax(np.abs(first.to_numpy() - second.to_numpy())) == pytest.approx(0.0)
    assert validate_trend_feature_causality(first, cutoff, meta["seasonal_baseline"])["status"] == "passed"


def test_seasonal_baseline_leakage_is_detected():
    dates = pd.date_range("2020-01-01", periods=10); frame = pd.DataFrame({"x": range(6)}, index=dates[:6])
    metadata = {"fit_end": dates[8].isoformat(), "validation_or_test_used": True}
    assert validate_trend_feature_causality(frame, dates[5], metadata)["seasonal_baseline_leakage"] is True
