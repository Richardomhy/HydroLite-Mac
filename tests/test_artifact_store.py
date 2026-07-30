from tests.runtime_helpers import configure_runtime


def test_artifact_discovery_preview_and_safe_bundle(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_db import create_run_record, list_artifact_records
    from hydrolite.runtime_paths import ensure_runtime_directories
    from hydrolite.artifact_store import create_artifact_bundle, discover_run_artifacts, preview_artifact, verify_artifact_bundle
    create_run_record(run_id="r", project_id="p", workflow_id="x", status="succeeded")
    paths = ensure_runtime_directories("r"); csv = paths["artifacts"]/"result.csv"; csv.write_text("x\\n1\\n")
    rows = discover_run_artifacts("r")
    assert rows and preview_artifact(csv)["status"] == "passed"
    csv.write_text("x\\n2\\n")
    discover_run_artifacts("r")
    paths_in_db = [row["path"] for row in list_artifact_records(run_id="r")]
    assert len(paths_in_db) == len(set(paths_in_db))
    bundle = create_artifact_bundle("r", tmp_path/"bundle.zip")
    assert verify_artifact_bundle(bundle)["status"] == "passed"
