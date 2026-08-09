from hydrolite.research_registry import NOTICE, built_in_sources
from hydrolite.source_licensing import audit_source_licenses


def test_research_records_are_clean_room_and_skill_license_is_missing():
    records = built_in_sources()
    assert len(records) == 5 and all(row["integration_mode"] == "method_inspired_clean_room" for row in records)
    assert "license_file_missing" in str(audit_source_licenses()) and "精确复现" in NOTICE


def test_m4_sources_keep_clean_room_provenance():
    records = {row["source_id"]: row for row in built_in_sources()}
    for source_id in ("physics_graph_temporal_residual_source", "trend_graph_multihorizon_water_quality_source"):
        assert records[source_id]["integration_mode"] == "method_inspired_clean_room"
        assert records[source_id]["provenance"]
