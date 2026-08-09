import numpy as np
import pandas as pd
import pytest

from hydrolite.trend_aware_features import build_causal_trend_features, build_lag_features, build_rolling_features, calculate_robust_local_trend, calculate_seasonal_baseline


def test_lag_rolling_and_robust_slope():
    dates = pd.date_range("2020-01-01", periods=10); values = np.arange(10.0)
    assert build_lag_features(values, (1,), dates).iloc[4, 0] == 3
    assert build_rolling_features(values, (3,), dates).iloc[4].rolling_sum_3 == 9
    assert calculate_robust_local_trend(values, 5, dates).iloc[-1] == pytest.approx(1.0)


def test_seasonal_baseline_is_training_only():
    dates = pd.date_range("2020-01-01", periods=730); values = np.sin(np.arange(730) * 2 * np.pi / 365)
    _, metadata = calculate_seasonal_baseline(values, dates, dates[0], dates[364])
    assert metadata["fit_end"] == dates[364].isoformat()
    assert metadata["validation_or_test_used"] is False


def test_causal_trend_feature_set_contains_expected_groups():
    dates = pd.date_range("2020-01-01", periods=100); frame, metadata = build_causal_trend_features(np.arange(100), dates, issue_time=dates[80], fit_end=dates[50])
    assert {"lag_1", "rolling_mean_7", "robust_local_slope", "seasonal_anomaly", "missingness_indicator"} <= set(frame)
    assert frame.index.max() == dates[80]
    assert metadata["causal"] is True
