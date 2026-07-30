from hydrolite.conservation import calculate_water_retention_amount, validate_conservation_scenario
def test_conservation_is_runoff_difference():
    assert calculate_water_retention_amount(10,3) == 7
    assert validate_conservation_scenario({"hydrolite_changes":{"cn_delta":-5}})
