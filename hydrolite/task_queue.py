from __future__ import annotations

from hydrolite.runtime_db import list_task_records, update_task_record
from hydrolite.task_engine import TERMINAL, execute_task, resolve_task_dependencies


_PAUSED = False
_MAX_PARALLEL = 1


def enqueue_task(task_id: str) -> dict:
    return update_task_record(task_id, status="queued")


def dequeue_next_task() -> dict | None:
    if _PAUSED:
        return None
    tasks = list_task_records()
    run_ids = {task["run_id"] for task in tasks if task["status"] in {"pending", "queued", "retrying"}}
    ready = set()
    for run_id in run_ids:
        ready.update(resolve_task_dependencies(run_id)["ready"])
    candidates = [task for task in reversed(tasks) if task["task_id"] in ready]
    return candidates[0] if candidates else None


def list_queued_tasks() -> list[dict]:
    return [task for task in list_task_records() if task["status"] in {"pending", "queued", "retrying"}]


def pause_queue() -> dict:
    global _PAUSED
    _PAUSED = True
    return get_queue_status()


def resume_queue() -> dict:
    global _PAUSED
    _PAUSED = False
    return get_queue_status()


def run_queue_once() -> dict:
    task = dequeue_next_task()
    if not task:
        return {"status": "idle", "task_id": None}
    result = execute_task(task["task_id"])
    return {"status": result.status, "task_id": task["task_id"]}


def run_queue_until_empty() -> dict:
    completed = []
    while not _PAUSED:
        result = run_queue_once()
        if result["status"] == "idle":
            break
        completed.append(result)
    run_ids = {task["run_id"] for task in list_task_records() if task["status"] in TERMINAL}
    from hydrolite.run_manager import finalize_run
    for run_id in run_ids:
        tasks = list_task_records(run_id=run_id)
        if tasks and all(task["status"] in TERMINAL for task in tasks):
            finalize_run(run_id)
    return {"status": "completed", "tasks_processed": len(completed), "results": completed}


def set_max_parallel_tasks(value: int) -> int:
    global _MAX_PARALLEL
    if value not in {1, 2}: raise ValueError("max_parallel_tasks must be 1 or 2")
    _MAX_PARALLEL = value
    return value


def get_queue_status() -> dict:
    return {"paused": _PAUSED, "max_parallel_tasks": _MAX_PARALLEL, "queued": len(list_queued_tasks())}


def recover_interrupted_tasks() -> dict:
    recovered = []
    for task in list_task_records():
        if task["status"] in {"running", "preparing"}:
            update_task_record(task["task_id"], status="interrupted", error_type="internal_error", error_message="Application stopped while task was running.")
            recovered.append(task["task_id"])
    return {"status": "passed", "interrupted": recovered}
