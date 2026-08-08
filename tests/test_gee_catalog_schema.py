from hydrolite.gee_catalog.loader import load_catalog_records
from hydrolite.gee_catalog.schema import GeeBandRecord, GeeDatasetRecord, validate_record


def test_catalog_fixture_has_required_schema(): assert all(not validate_record(row) for row in load_catalog_records())


def test_schema_types_accept_null_optional_metadata():
    assert GeeBandRecord(name="band").unit is None
    assert GeeDatasetRecord(asset_id="TEST/ID").asset_id == "TEST/ID"
