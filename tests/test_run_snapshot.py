from tests.runtime_helpers import configure_runtime


def test_run_snapshot_and_reproduction_bundle_are_safe(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_db import create_run_record
    from hydrolite.runtime_paths import ensure_runtime_directories
    from hydrolite.run_snapshot import create_run_configuration_snapshot, create_run_input_snapshot, export_reproduction_package, verify_run_snapshot
    create_run_record(run_id="r", project_id="p", workflow_id="x", status="succeeded")
    paths=ensure_runtime_directories("r"); (paths["configuration"]/"config.json").write_text("{}")
    assert create_run_input_snapshot("r") != create_run_configuration_snapshot("r")
    assert verify_run_snapshot("r")["status"] == "passed"
    bundle=export_reproduction_package("r", tmp_path/"repro.zip")
    import zipfile
    assert not any(name.endswith((".sqlite3",".dss",".h5")) for name in zipfile.ZipFile(bundle).namelist())
