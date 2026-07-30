import numpy as np

from hydrolite.data_assimilation import initialize_enkf_ensemble, update_enkf_ensemble


def test_enkf_update_is_bounded_and_nonnegative():
    config = {"ensemble_size": 10, "observation_error": .8, "model_error": .2, "random_seed": 1}
    ensemble = initialize_enkf_ensemble({"routing_flow": 4, "baseflow": 1, "model_flow_correction_factor": 1}, {}, config)
    result = update_enkf_ensemble(ensemble, 5, config)
    assert result["states"].shape[0] == 10
    assert np.all(result["states"] >= 0)
    assert result["posterior_spread"] >= 0
