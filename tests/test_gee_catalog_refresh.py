from hydrolite.gee_catalog import refresh_catalog, validate_catalog


def test_catalog_refresh_is_explicit_and_valid():
    assert refresh_catalog("dry-run")["status"] == "dry_run"
    assert refresh_catalog("execute")["status"] == "refreshed_offline_fixture"
    assert validate_catalog()["status"] == "passed"
