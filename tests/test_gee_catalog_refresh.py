from pathlib import Path

from hydrolite.gee_catalog import refresh_catalog, validate_catalog
from hydrolite.gee_catalog.loader import fixture_records
from hydrolite.gee_catalog.updater import activate_catalog_candidate, build_catalog_candidate, rollback_catalog_refresh


def _records(count=None):
    rows = fixture_records()
    count = count or len(rows) + 1
    while len(rows) < count:
        row = dict(rows[0]); row["asset_id"] = f"TEST/EXTRA_{len(rows)}"; rows.append(row)
    return rows


def test_catalog_refresh_is_explicit_and_preserves_previous_catalog(tmp_path: Path):
    assert refresh_catalog("dry-run")["status"] in {"dry_run", "refresh_failed_previous_catalog_preserved"}
    remote = {"source_url": "https://storage.googleapis.com/earthengine-stac/catalog.json", "http_status": 200}
    first = build_catalog_candidate(tmp_path / "stage-one", _records(), [], remote)
    assert activate_catalog_candidate(first, tmp_path / "live")["status"] == "refreshed"
    second = build_catalog_candidate(tmp_path / "stage-two", _records(len(fixture_records()) + 2), [], remote)
    assert activate_catalog_candidate(second, tmp_path / "live")["status"] == "refreshed"
    assert rollback_catalog_refresh(tmp_path / "live")["status"] == "rolled_back"
    assert validate_catalog(_records(), first["manifest"])["status"] in {"valid", "valid_with_warnings"}


def test_dry_run_does_not_create_a_catalog(tmp_path: Path):
    root = tmp_path / "missing-catalog"
    result = refresh_catalog("dry-run", catalog_root=root)
    assert result["status"] in {"dry_run", "refresh_failed_previous_catalog_preserved"}
    assert not root.exists()
