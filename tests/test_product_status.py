from hydrolite.product_status import get_product_feature_status, product_status_summary


def test_product_status_does_not_upgrade_synthetic_or_framework_evidence():
    gamma = get_product_feature_status("gamma_lag_features")
    assert gamma.status == "experimental" and gamma.validation_level == "synthetic_demo" and gamma.real_data_tested is False
    water_quality = get_product_feature_status("water_quality")
    assert water_quality.status == "planned" and water_quality.real_data_tested is False
    assert "Runnable does not imply" in product_status_summary()["rule"]


def test_negative_method_evidence_remains_visible():
    trend = get_product_feature_status("trend_aware_features")
    susceptibility = get_product_feature_status("flood_susceptibility_xai")
    assert any("not demonstrated" in item for item in trend.limitations)
    assert any("unstable" in item and "rl_not_justified" in item for item in susceptibility.limitations)
