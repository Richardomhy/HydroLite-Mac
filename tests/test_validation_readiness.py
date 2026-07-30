from hydrolite.validation_readiness import assess_hindcast_readiness


def test_synthetic_demo_never_claims_real_validation():
    from hydrolite.ui.pages import hindcast_validation

    assert callable(hindcast_validation.render)
    result = assess_hindcast_readiness("data_demo/hindcast_validation")
    assert result["event_count"] == 6
    assert result["validation_level"] == "framework_ready_real_data_missing"
    assert result["operational_readiness"] is False
