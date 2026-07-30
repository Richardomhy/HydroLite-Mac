import numpy as np


def test_hybrid_residual_and_nonnegative():
    from hydrolite.hybrid_forecast import apply_residual_correction, build_physics_residual_target

    observed = np.array([1, 3, 2], float)
    physics = np.array([2, 2, 4], float)
    residual = build_physics_residual_target(observed, physics)
    corrected = apply_residual_correction(physics, residual)
    assert np.allclose(corrected, observed)
    assert (apply_residual_correction([0], [-2]) >= 0).all()
