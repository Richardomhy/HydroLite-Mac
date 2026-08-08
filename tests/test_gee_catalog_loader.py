from pathlib import Path

from hydrolite.gee_catalog.loader import get_catalog_dataset, inspect_catalog_availability, load_catalog_records, load_test_fixture


def test_fixture_loader_and_lookup_are_offline_safe():
    payload = load_test_fixture()
    assert payload["records"]
    assert get_catalog_dataset("UCSB-CHG/CHIRPS/DAILY")["asset_id"] == "UCSB-CHG/CHIRPS/DAILY"
    assert inspect_catalog_availability()["status"] in {"fixture_only", "available", "official_complete", "official_complete_with_warnings"}
    assert len(load_catalog_records()) >= 4
