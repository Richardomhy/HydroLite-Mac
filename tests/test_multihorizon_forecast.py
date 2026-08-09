import numpy as np

from hydrolite.multihorizon_forecast import build_direct_forecast, build_forecast_horizons, build_hybrid_forecast, build_recursive_forecast, fit_direct_models, fit_linear_model, select_hybrid_weights


def test_direct_models_cover_requested_horizons():
    values = np.linspace(1, 20, 100); features = np.column_stack([np.roll(values, 1), np.roll(values, 2)])[2:]; target = values[2:]
    models = fit_direct_models(features[:-12], target[:-12], (1, 3, 6, 12), feature_names=["lag1", "lag2"])
    result = build_direct_forecast(models, features[-1])
    assert set(result) == {1, 3, 6, 12}
    assert build_forecast_horizons((12, 1, 3, 6)) == [1, 3, 6, 12]


def test_recursive_distinguishes_observed_and_predicted_history():
    model = fit_linear_model([[1, 0], [2, 1], [3, 2], [4, 3]], [2, 3, 4, 5], ["lag1", "lag2"])
    result = build_recursive_forecast(model, [1, 2, 3, 4, 5], (1, 3), lag_count=2)
    assert result["future_observations_used"] is False
    assert result["predicted_history_count"] == 3


def test_hybrid_weights_are_nonnegative_and_sum_to_one():
    values = {1: np.array([1.0, 2.0]), 3: np.array([2.0, 3.0])}; direct = {key: value + .1 for key, value in values.items()}; recursive = {key: value + .3 for key, value in values.items()}
    weights = select_hybrid_weights(direct, recursive, values, "validation_optimized_simplex")
    hybrid = build_hybrid_forecast({h: float(direct[h][0]) for h in values}, {h: float(recursive[h][0]) for h in values}, weights)
    assert set(hybrid) == set(values)
    assert all(abs(row["direct"] + row["recursive"] - 1) < 1e-12 and min(row["direct"], row["recursive"]) >= 0 for row in weights.values())
