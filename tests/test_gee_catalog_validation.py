from hydrolite.gee_catalog.loader import fixture_records
from hydrolite.gee_catalog.validation import validate_catalog, validate_unique_asset_ids


def test_catalog_validation_detects_duplicate_ids_and_fixture_state():
    rows = fixture_records()
    assert validate_catalog()["status"] == "fixture_only"
    assert validate_unique_asset_ids(rows + [dict(rows[0])])
