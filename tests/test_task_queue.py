import sys
from tests.runtime_helpers import configure_runtime


def test_queue_fifo_pause_resume(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.runtime_db import create_run_record
    from hydrolite.task_engine import create_task
    from hydrolite.task_queue import enqueue_task, pause_queue, resume_queue, run_queue_until_empty
    create_run_record(run_id="r", project_id="p", workflow_id="x", status="created")
    ids = [create_task({"stage_id":str(i),"display_name":str(i),"task_type":"subprocess","command":[sys.executable,"-c","print('ok')"],"timeout":5},"r")["task_id"] for i in range(2)]
    for task_id in ids: enqueue_task(task_id)
    assert pause_queue()["paused"]
    assert resume_queue()["paused"] is False
    assert run_queue_until_empty()["tasks_processed"] == 2
