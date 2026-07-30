from hydrolite.groundwater import calculate_baseflow, calculate_deep_groundwater_loss, initialize_groundwater_state, update_groundwater_state


def test_groundwater_recession_nonnegative():
    parameters={"initial_groundwater_storage":100,"baseflow_coefficient":0.1,"deep_loss_coefficient":0.02}
    state=initialize_groundwater_state(parameters)
    flux={"groundwater_recharge_mm":5,"baseflow_mm":calculate_baseflow(state,parameters),"deep_loss_mm":calculate_deep_groundwater_loss(state,parameters)}
    assert update_groundwater_state(state,flux)["groundwater_storage_mm"]>=0
