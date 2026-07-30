from hydrolite.soil_water import DEMO_SOIL_PARAMETERS, calculate_infiltration, initialize_soil_state, validate_soil_parameters


def test_soil_parameter_order_and_infiltration():
    assert validate_soil_parameters(DEMO_SOIL_PARAMETERS)["status"]=="passed"
    bad={**DEMO_SOIL_PARAMETERS,"wilting_point":0.4}
    assert validate_soil_parameters(bad)["status"]=="failed"
    state=initialize_soil_state(DEMO_SOIL_PARAMETERS)
    assert 0<=calculate_infiltration(20,state,DEMO_SOIL_PARAMETERS)<=20
