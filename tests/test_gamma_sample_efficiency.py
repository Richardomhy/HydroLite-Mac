from hydrolite.gamma_benchmark import run_sample_efficiency


def test_sample_windows_are_chronological_with_fixed_test(tmp_path):
    result = run_sample_efficiency(tmp_path)
    metrics = result["metrics"]
    assert list(metrics["training_fraction"]) == [1.0, .5, .25, .1]
    assert metrics["test_start_index"].nunique() == 1
    assert not metrics["temporal_shuffle"].any()
    assert metrics.iloc[-1]["status"] == "insufficient_sample"
    assert (metrics.iloc[:3]["NSE"] >= .99).all()
    assert (result["stability"]["status"] == "stable").all()
