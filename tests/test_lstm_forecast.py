import numpy as np


def test_lstm_sequence_shape_and_optional_environment(tmp_path):
    from hydrolite.lstm_forecast import build_lstm_sequences, detect_torch_environment, run_lstm_synthetic_smoke_test

    values = np.arange(80, dtype=float).reshape(40, 2)
    x, y = build_lstm_sequences(values, lookback=6, horizon=3, features=None, target=1)
    assert x.shape == (32, 6, 2)
    assert y.shape == (32, 3)
    environment = detect_torch_environment()
    result = run_lstm_synthetic_smoke_test(tmp_path)
    assert result["status"] in {"passed", "skipped_optional_dependency", "timeout"}
    if not environment["torch_available"]:
        assert result["status"] == "skipped_optional_dependency"
