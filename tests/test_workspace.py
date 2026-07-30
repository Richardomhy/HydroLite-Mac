from pathlib import Path


def test_workspace_manifest_raw_lock_and_snapshot(tmp_path: Path):
    from hydrolite.workspace import calculate_file_checksum, create_workspace, create_workspace_snapshot, restore_workspace_snapshot, validate_workspace

    root = tmp_path / "workspace"
    create_workspace(root, "Test Project")
    raw = root / "raw" / "source.csv"
    raw.write_text("a\n1\n", encoding="utf-8")
    checksum = calculate_file_checksum(raw)
    assert len(checksum) == 64
    assert validate_workspace(root)["status"] == "passed"
    snapshot = create_workspace_snapshot(root, tmp_path / "snapshot.zip")
    preview = restore_workspace_snapshot(snapshot, tmp_path / "restored", execute=False)
    assert preview["status"] == "dry_run"


def test_workspace_refuses_nonempty_and_data_raw(tmp_path: Path):
    from hydrolite.workspace import create_workspace

    root = tmp_path / "existing"
    root.mkdir()
    (root / "keep.txt").write_text("keep")
    try:
        create_workspace(root, "No overwrite")
    except FileExistsError:
        pass
    else:
        raise AssertionError("Existing workspace was overwritten")
