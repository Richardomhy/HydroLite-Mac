import numpy as np

from hydrolite.gamma_lag_features import build_gamma_feature_series, build_gamma_kernel, convolve_causal_series, detect_gamma_future_leakage


def test_future_input_changes_do_not_change_past_features():
    source = np.arange(60, dtype=float); kernel = build_gamma_kernel(2.5, 2, 20, 1)
    original = convolve_causal_series(source, kernel); modified = source.copy(); modified[31:] += 999
    changed = convolve_causal_series(modified, kernel)
    assert np.array_equal(original[:31], changed[:31])
    assert detect_gamma_future_leakage(source, kernel, 30)["status"] == "passed"


def test_zero_padding_warmup_and_hour_day_timesteps():
    kernel = build_gamma_kernel(2, 3, 10, 1); feature = build_gamma_feature_series([1, 0, 0], kernel)
    assert feature.loc[0, "is_warmup"]
    assert feature.loc[0, "effective_history_length"] == 1
    assert feature.loc[0, "available_kernel_fraction"] < 1
    assert np.isclose(feature.loc[0, "gamma_feature"], kernel[0])
    hourly = build_gamma_kernel(2, 6, 24, 1); daily = build_gamma_kernel(2, .25, 24, 1 / 24)
    assert np.isclose(hourly.sum(), 1) and np.isclose(daily.sum(), 1)
