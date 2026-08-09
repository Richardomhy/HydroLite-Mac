import numpy as np

from hydrolite.water_quality_evaluation import build_empirical_uncertainty, calculate_threshold_diagnostics, calculate_water_quality_metrics


def test_metrics_include_concentration_specific_diagnostics():
    result = calculate_water_quality_metrics([1, 2, 3, 4], [1.1, 1.9, 3.2, 3.8])
    assert {"RMSE", "MAE", "R2", "NSE", "KGE", "PBIAS", "Spearman", "peak_error", "peak_timing_error", "high_value_recall", "low_value_bias"}.issubset(result)


def test_threshold_is_explicitly_diagnostic_only():
    result = calculate_threshold_diagnostics([0, 2, 3], [0, 1, 3], 1.5)
    assert result["threshold_type"] == "diagnostic_only"
    assert {"precision", "recall", "F1", "false_alarm_rate"}.issubset(result)


def test_uncertainty_uses_validation_residuals_only():
    lower, upper, meta = build_empirical_uncertainty([1, 2, 3], [1, 1.8, 3.2], [2, 4])
    assert np.all(lower <= upper)
    assert meta["uncertainty_type"] == "empirical_validation_residual_interval"
    assert meta["fit_data"] == "validation_only"
    assert not meta["test_used"]
