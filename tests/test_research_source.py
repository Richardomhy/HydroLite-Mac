from hydrolite.research_intake import get_source, list_sources
from hydrolite.research_validation import validate_source


def test_registered_sources_are_metadata_only_and_clean_room():
    sources = list_sources()
    assert len(sources) == 5
    assert all(not source.full_text_local_reference for source in sources)
    assert all(not source.copy_allowed and not source.runtime_dependency_allowed for source in sources)
    assert all(not validate_source(source) for source in sources)


def test_incomplete_source_remains_explicitly_incomplete():
    source = get_source("trend_graph_multihorizon_water_quality_source")
    assert source.verification_status == "source_incomplete"
    assert source.doi is None
