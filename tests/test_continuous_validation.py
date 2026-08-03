from hydrolite.continuous_validation import evaluate_water_quality_hydrology_gate

def test_gate_default_is_blocked():
    assert evaluate_water_quality_hydrology_gate({})["status"]=="blocked"
