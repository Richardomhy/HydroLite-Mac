import sys
from tests.runtime_helpers import configure_runtime


def test_subprocess_success_failure_timeout_and_shell_guard(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_db import create_run_record
    from hydrolite.task_engine import create_task, execute_task, validate_task
    create_run_record(run_id="run1", project_id="p", workflow_id="test", status="created")
    ok = create_task({"stage_id":"ok","display_name":"ok","task_type":"subprocess","command":[sys.executable,"-c","print('ok')"],"timeout":5}, "run1")
    fail = create_task({"stage_id":"fail","display_name":"fail","task_type":"subprocess","command":[sys.executable,"-c","import sys;sys.exit(3)"],"timeout":5}, "run1")
    slow = create_task({"stage_id":"slow","display_name":"slow","task_type":"subprocess","command":[sys.executable,"-c","import time;time.sleep(2)"],"timeout":1}, "run1")
    assert execute_task(ok["task_id"]).status == "succeeded"
    assert execute_task(fail["task_id"]).status == "failed"
    assert execute_task(slow["task_id"]).status == "timed_out"
    assert validate_task({"task_type":"subprocess","command":"echo unsafe","timeout":1})["status"] == "failed"


def test_task_cancel_and_retry(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.process_manager import start_managed_process
    from hydrolite.runtime_db import create_run_record, update_task_record
    from hydrolite.task_engine import cancel_task, create_task, retry_task
    create_run_record(run_id="run2", project_id="p", workflow_id="test", status="created")
    task = create_task({"stage_id":"cancel","display_name":"cancel","task_type":"subprocess","command":[sys.executable,"-c","print('x')"],"timeout":5,"retry_policy":{"max_attempts":2}}, "run2")
    pid = start_managed_process([sys.executable,"-c","import time;time.sleep(30)"], tmp_path, {}, tmp_path/"out", tmp_path/"err")
    update_task_record(task["task_id"], status="running", process_id=pid, attempt=1)
    assert cancel_task(task["task_id"])["process_stopped"]
    assert retry_task(task["task_id"])["status"] == "retrying"
