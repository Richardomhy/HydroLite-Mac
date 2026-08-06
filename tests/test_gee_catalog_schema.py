from hydrolite.gee_catalog.loader import load_catalog
from hydrolite.gee_catalog.schema import validate_record


def test_catalog_fixture_has_required_schema(): assert all(not validate_record(row) for row in load_catalog())
