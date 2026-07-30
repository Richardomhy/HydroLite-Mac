import numpy as np
import pandas as pd

from hydrolite.hindcast_metrics import calculate_hindcast_metrics


def test_full_hydrograph_metrics_are_finite():
    observed = np.array([1, 2, 5, 3, 1], dtype=float)
    result = calculate_hindcast_metrics(observed, observed * 1.02, pd.date_range("2024-01-01", periods=5, freq="h"))
    assert result["summary"]["NSE"] > 0.9
    assert result["summary"]["sample_count"] == 5
