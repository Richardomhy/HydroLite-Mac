from tests.delivery_helpers import make_delivery_workspace


def test_referenced_data_snapshot_reads_metadata_without_modifying_input(monkeypatch, tmp_path):
    workspace = make_delivery_workspace(monkeypatch, tmp_path)
    source = workspace / "data" / "rain.csv"
    before = source.read_bytes()
    from hydrolite.project_versioning import create_data_snapshot
    snapshot = create_data_snapshot(workspace)
    assert source.read_bytes() == before
    assert snapshot["snapshot_mode"] == "referenced"
    assert snapshot["dataset_ids"]
    assert list(snapshot["row_counts"].values()) == [2]
    assert all(not value.startswith("/") for value in snapshot["source_paths"].values())
    assert all("minghenyu" not in value for value in snapshot["source_paths"].values())
