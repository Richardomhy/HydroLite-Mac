from hydrolite.data_assimilation import assimilate_flow_nudging, validate_assimilation_config


def test_nudging_gain_and_analysis():
    result = assimilate_flow_nudging(10, 14, {"gain": .5})
    assert result["analysis"] == 12
    assert validate_assimilation_config({"gain": 2, "ensemble_size": 20, "observation_error": 1, "model_error": 1})["status"] == "failed"
