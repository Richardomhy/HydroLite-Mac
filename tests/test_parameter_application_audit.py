from hydrolite.parameter_application_audit import trace_parameter_from_config

def test_trace_configured_parameter():
    assert trace_parameter_from_config("et_coefficient",{"parameters":{"et_coefficient":1}})["configured"]
