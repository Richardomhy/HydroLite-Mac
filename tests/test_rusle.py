from hydrolite.rusle import ROOT, calculate_rusle_soil_loss, run_rusle, validate_rusle_outputs
def test_rusle_demo(tmp_path):
    assert calculate_rusle_soil_loss(2,3,4,5,6) == 720
    run_rusle(ROOT/"data_demo/rusle/demo_rusle_config.yaml",tmp_path)
    assert validate_rusle_outputs(tmp_path)["status"] == "passed"
