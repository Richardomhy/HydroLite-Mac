def test_return_code_is_not_enough_when_required_output_missing(tmp_path):
    from hydrolite.artifact_validation import validate_report_artifact, validate_table_artifact
    missing = tmp_path/"missing.csv"
    assert validate_table_artifact(missing)["status"] == "invalid"
    empty = tmp_path/"report.md"; empty.write_text("")
    assert validate_report_artifact(empty)["status"] == "invalid"


def test_empty_stderr_log_is_valid(monkeypatch, tmp_path):
    from tests.runtime_helpers import configure_runtime
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.artifact_store import register_artifact
    from hydrolite.artifact_validation import validate_run_artifacts
    from hydrolite.runtime_db import create_run_record
    create_run_record(run_id="r", project_id="p", workflow_id="x", status="succeeded")
    log = tmp_path / "stderr.log"; log.write_text("")
    register_artifact("r", None, log)
    assert validate_run_artifacts("r")["status"] == "valid"
