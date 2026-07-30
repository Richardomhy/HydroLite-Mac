from tests.runtime_helpers import configure_runtime


def test_interrupted_run_recovery(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_db import create_run_record, create_task_record, get_run_record
    from hydrolite.runtime_recovery import recover_interrupted_run, validate_recovery_result
    create_run_record(run_id="r", project_id="p", workflow_id="x", status="running")
    create_task_record(task_id="t", run_id="r", stage_id="x", status="running", command={})
    assert recover_interrupted_run("r")["status"] == "passed"
    assert get_run_record("r")["status"] == "interrupted"
    assert validate_recovery_result("r")["status"] == "passed"
