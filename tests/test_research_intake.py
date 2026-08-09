import pytest

from hydrolite.research_intake import assess_method_readiness, get_method, get_source, register_source, search_sources


def test_intake_search_and_readiness_are_configuration_backed():
    assert search_sources("Gamma")[0].source_id == "gamma_lag_hydrologic_prior_source"
    readiness = assess_method_readiness(get_method("gamma_lag_hydrologic_prior"))
    assert readiness["readiness"] == "clean_room_ready"


def test_duplicate_source_registration_is_rejected():
    source = get_source("gamma_lag_hydrologic_prior_source")
    with pytest.raises(ValueError, match="Duplicate"):
        register_source(source, [source])
