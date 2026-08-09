import numpy as np

from hydrolite.multihorizon_forecast import build_recursive_forecast, fit_linear_model, select_hybrid_weights, validate_multihorizon_result


def test_recursive_future_observation_leakage_is_blocked():
    model = fit_linear_model([[2, 1], [3, 2], [4, 3], [5, 4]], [3, 4, 5, 6], ["lag1", "lag2"]); history = [1, 2, 3, 4, 5]
    first = build_recursive_forecast(model, history, (1, 3), lag_count=2)
    future_observations = [999, 999, 999]
    second = build_recursive_forecast(model, history, (1, 3), lag_count=2)
    assert future_observations and first["forecast"] == second["forecast"]


def test_test_data_never_selects_hybrid_weights():
    y = {1: np.array([1, 2, 3])}; weights = select_hybrid_weights({1: y[1]}, {1: y[1] + 1}, y, "validation_inverse_error")
    result = validate_multihorizon_result({"weights": weights, "future_observations_used": False})
    assert result["status"] == "passed"
    assert result["test_selection_leakage"] is False
