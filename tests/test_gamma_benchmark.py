from hydrolite.gamma_benchmark import run_gamma_benchmark


def test_benchmarks_use_fixed_test_and_gamma_adds_synthetic_value(tmp_path):
    result = run_gamma_benchmark(tmp_path)
    models = set(result["metrics"]["model"])
    assert {"Raw", "Rolling", "Exponential", "Linear Reservoir", "Gamma Single", "Gamma Multi"} <= models
    assert result["synthetic_value_added"] == "demonstrated"
    assert result["real_data_value_added"] == "not_tested"
    assert all(result["comparisons"].values())
    assert {"NSE", "KGE", "RMSE", "MAE", "PBIAS", "peak_error", "timing_error", "volume_error", "parameter_count", "compute_time_seconds", "warmup_steps"} <= set(result["metrics"].columns)
