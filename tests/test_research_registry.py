from hydrolite.research_registry import NOTICE, built_in_sources
from hydrolite.source_licensing import audit_source_licenses


def test_research_records_are_clean_room_and_skill_license_is_missing():
    assert len(built_in_sources()) == 4 and all(row["implementation_mode"] == "method_inspired_clean_room" for row in built_in_sources())
    assert "license_file_missing" in str(audit_source_licenses()) and "精确复现" in NOTICE
