import numpy as np

from hydrolite.flood_susceptibility_models import select_calibration_on_validation


def test_calibration_is_validation_only_and_returns_probabilities():
    observed = np.array([0, 0, 0, 1, 1, 1] * 10)
    raw = np.linspace(.05, .95, len(observed))
    calibrator, metrics = select_calibration_on_validation(observed, raw)
    calibrated = calibrator.predict(raw)
    assert set(metrics.fit_split) == {"validation"}
    assert not metrics.test_used.any()
    assert ((calibrated >= 0) & (calibrated <= 1)).all()
