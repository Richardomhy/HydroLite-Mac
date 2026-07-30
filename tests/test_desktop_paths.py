from hydrolite.desktop import desktop_paths


def test_desktop_paths_and_migration_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / ".hydrolite"
    legacy.mkdir()
    (legacy / "keep.txt").write_text("original", encoding="utf-8")
    monkeypatch.setenv("HYDROLITE_LEGACY_RUNTIME", str(legacy))
    assert "Library/Application Support/HydroLite Studio" in str(desktop_paths.get_application_support_dir())
    plan = desktop_paths.execute_legacy_runtime_migration()
    assert plan["status"] == "dry_run"
    assert (legacy / "keep.txt").read_text() == "original"
