from pathlib import Path


def test_workspace_quality_ready_and_raw_unchanged(tmp_path: Path):
    from hydrolite.data_quality_center import run_workspace_quality_checks
    from hydrolite.data_upload import copy_upload_to_workspace
    from hydrolite.workspace import calculate_file_checksum, create_workspace

    root = tmp_path / "workspace"
    create_workspace(root, "Quality")
    record = copy_upload_to_workspace("templates/data_upload/rainfall_observed.csv", root)
    raw = root / record["raw_path"]
    before = calculate_file_checksum(raw)
    result = run_workspace_quality_checks(root)
    assert result["status"] in {"ready", "ready_with_warnings"}
    assert calculate_file_checksum(raw) == before
    assert (root / "standardized" / "rainfall_observed.csv").exists()
