from tests.runtime_helpers import configure_runtime, make_workspace


def test_run_optional_failure_finalizes_with_warning(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.project_service import register_workspace_as_project
    from hydrolite.run_manager import create_run, start_run, validate_run
    from hydrolite.runtime_db import get_run_record, list_task_records
    from hydrolite.task_queue import run_queue_until_empty
    project = register_workspace_as_project(make_workspace(tmp_path))
    run = create_run(project["project_id"], "data_preparation", {"run_mode":"test"})
    start_run(run["run_id"]); run_queue_until_empty()
    assert get_run_record(run["run_id"])["status"] == "succeeded_with_warnings"
    assert validate_run(run["run_id"])["status"] == "passed"
    assert sum(task["status"] == "failed" for task in list_task_records(run_id=run["run_id"])) == 1
