from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
import json
import subprocess
import time
import traceback
import uuid

from hydrolite.process_manager import (
    start_managed_process,
    terminate_managed_process,
    wait_managed_process,
)
from hydrolite.runtime_db import (
    add_task_dependency,
    create_runtime_event,
    create_task_record,
    get_task_record,
    list_task_dependencies,
    update_task_record,
)
from hydrolite.runtime_logging import log_runtime_event
from hydrolite.runtime_mode import validate_task_for_mode
from hydrolite.runtime_paths import ensure_runtime_directories, get_task_dir
from hydrolite.task_models import TaskResult, TaskSpec


TERMINAL = {"succeeded", "succeeded_with_warnings", "failed", "timed_out", "cancelled", "blocked", "skipped"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _spec_from_record(record: dict) -> dict:
    value = record.get("command")
    if isinstance(value, dict):
        return value
    return json.loads(value) if isinstance(value, str) else {}


def validate_task(task_spec: TaskSpec | dict) -> dict:
    spec = task_spec.as_dict() if isinstance(task_spec, TaskSpec) else task_spec
    errors = []
    if spec.get("task_type") == "subprocess":
        command = spec.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            errors.append("subprocess command must be a non-empty string array")
    if int(spec.get("timeout", 0)) <= 0:
        errors.append("timeout must be positive")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def create_task(task_spec: TaskSpec | dict, run_id: str) -> dict:
    spec = task_spec.as_dict() if isinstance(task_spec, TaskSpec) else dict(task_spec)
    validation = validate_task(spec)
    if validation["status"] != "passed":
        raise ValueError("; ".join(validation["errors"]))
    task_id = f"tsk_{uuid.uuid4().hex[:12]}"
    paths = ensure_runtime_directories(run_id, task_id)
    task_dir = paths["task"]
    record = create_task_record(
        task_id=task_id,
        run_id=run_id,
        stage_id=spec["stage_id"],
        task_type=spec.get("task_type", "subprocess"),
        display_name=spec["display_name"],
        command=spec,
        working_directory=str(task_dir / "work"),
        status="pending",
        attempt=0,
        max_attempts=spec.get("retry_policy", {}).get("max_attempts", 1),
        timeout_seconds=spec.get("timeout", 300),
        stdout_path=str(task_dir / "stdout.log"),
        stderr_path=str(task_dir / "stderr.log"),
        output_manifest={},
        retryable=False,
        cancelled_by_user=False,
    )
    (task_dir / "task_manifest.json").write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    create_runtime_event(run_id, task_id, "task_created", "pending")
    return record


def resolve_task_dependencies(run_id: str) -> dict:
    from hydrolite.runtime_db import list_task_records
    tasks = {row["task_id"]: row for row in list_task_records(run_id=run_id)}
    ready, blocked = [], []
    for task_id, task in tasks.items():
        if task["status"] not in {"pending", "queued", "retrying"}:
            continue
        deps = list_task_dependencies(task_id)
        required_failed = [dep for dep in deps if dep["required"] and tasks.get(dep["depends_on_task_id"], {}).get("status") in {"failed", "timed_out", "cancelled", "blocked"}]
        waiting = [dep for dep in deps if tasks.get(dep["depends_on_task_id"], {}).get("status") not in TERMINAL]
        if required_failed:
            mark_task_blocked(task_id, f"Required dependency failed: {required_failed[0]['depends_on_task_id']}")
            blocked.append(task_id)
        elif not waiting:
            ready.append(task_id)
    return {"ready": ready, "blocked": blocked}


def execute_python_task(task_spec: dict) -> TaskResult:
    started = time.monotonic()
    handler = task_spec.get("handler")
    if not handler or ":" not in handler:
        return TaskResult(status="failed", errors=["Python handler must use module:function syntax."])
    try:
        module_name, function_name = handler.split(":", 1)
        result = getattr(import_module(module_name), function_name)(**task_spec.get("arguments", {}))
        outputs = [str(item) for item in result.get("outputs", [])] if isinstance(result, dict) else []
        return TaskResult(status="succeeded", outputs=outputs, runtime_seconds=time.monotonic() - started)
    except Exception:
        return TaskResult(status="failed", errors=[traceback.format_exc()], runtime_seconds=time.monotonic() - started)


def execute_subprocess_task(task_spec: dict, task_record: dict | None = None) -> TaskResult:
    validation = validate_task(task_spec)
    if validation["status"] != "passed":
        return TaskResult(status="failed", errors=validation["errors"])
    record = task_record or {}
    cwd = Path(record.get("working_directory") or Path.cwd())
    stdout = Path(record.get("stdout_path") or cwd / "stdout.log")
    stderr = Path(record.get("stderr_path") or cwd / "stderr.log")
    started = time.monotonic()
    pid = start_managed_process(task_spec["command"], cwd, task_spec.get("environment"), stdout, stderr)
    if record.get("task_id"):
        update_task_record(record["task_id"], process_id=pid)
    try:
        return_code = wait_managed_process(pid, timeout=float(task_spec.get("timeout", 300)))
    except subprocess.TimeoutExpired:
        terminate_managed_process(pid)
        return TaskResult(status="timed_out", errors=[f"Task exceeded timeout of {task_spec.get('timeout')} seconds."], runtime_seconds=time.monotonic() - started)
    status = "succeeded" if return_code == 0 else "failed"
    errors = [] if return_code == 0 else [stderr.read_text(encoding="utf-8", errors="replace")[-4000:] or f"Process exited with {return_code}"]
    return TaskResult(status=status, return_code=return_code, errors=errors, runtime_seconds=time.monotonic() - started)


def execute_qgis_task(task_spec: dict) -> TaskResult: return execute_subprocess_task(task_spec)
def execute_hec_hms_task(task_spec: dict) -> TaskResult: return execute_subprocess_task(task_spec)
def execute_swmm_task(task_spec: dict) -> TaskResult: return execute_subprocess_task(task_spec)


def execute_task(task_id: str) -> TaskResult:
    record = get_task_record(task_id)
    if not record:
        raise KeyError(f"Unknown task_id: {task_id}")
    spec = _spec_from_record(record)
    mode_check = validate_task_for_mode(spec)
    if mode_check["status"] == "blocked":
        mark_task_blocked(task_id, mode_check["reason"])
        return TaskResult(status="blocked", errors=[mode_check["reason"]])
    attempt = int(record.get("attempt") or 0) + 1
    update_task_record(task_id, status="running", attempt=attempt, started_at=_now(), progress=0)
    create_runtime_event(record["run_id"], task_id, "task_status", "running")
    log_runtime_event(record["run_id"], task_id, "INFO", f"Task started: {record['display_name']}")
    result = execute_python_task(spec) if spec.get("task_type") == "python_function" else execute_subprocess_task(spec, record)
    error_message = result.errors[-1][-4000:] if result.errors else ""
    update_task_record(
        task_id,
        status=result.status,
        finished_at=_now(),
        return_code=result.return_code,
        progress=100 if result.status.startswith("succeeded") else 0,
        error_type="" if not result.errors else ("timeout" if result.status == "timed_out" else "external_backend_failed"),
        error_message=error_message,
        retryable=result.status in {"timed_out", "failed"} and attempt < int(record.get("max_attempts") or 1),
        output_manifest={"outputs": result.outputs, "runtime_seconds": result.runtime_seconds},
    )
    create_runtime_event(record["run_id"], task_id, "task_status", result.status, error_message)
    log_runtime_event(record["run_id"], task_id, "ERROR" if result.status in {"failed", "timed_out"} else "INFO", f"Task finished: {result.status}")
    collect_task_outputs(task_id)
    return result


def cancel_task(task_id: str) -> dict:
    record = get_task_record(task_id)
    if not record:
        raise KeyError(task_id)
    pid = record.get("process_id")
    stopped = terminate_managed_process(int(pid)) if pid else True
    updated = update_task_record(task_id, status="cancelled", cancelled_by_user=True, finished_at=_now(), error_type="cancelled", error_message="Cancelled by user.")
    create_runtime_event(record["run_id"], task_id, "task_status", "cancelled")
    return {"status": "cancelled", "process_stopped": stopped, "task": updated}


def retry_task(task_id: str) -> dict:
    record = get_task_record(task_id)
    if not record:
        raise KeyError(task_id)
    if int(record.get("attempt") or 0) >= int(record.get("max_attempts") or 1):
        return {"status": "not_retryable", "task_id": task_id}
    return update_task_record(task_id, status="retrying", error_type="", error_message="", return_code=None, cancelled_by_user=False)


def mark_task_blocked(task_id: str, reason: str) -> dict:
    record = get_task_record(task_id)
    updated = update_task_record(task_id, status="blocked", finished_at=_now(), error_type="dependency_failed", error_message=reason)
    if record:
        create_runtime_event(record["run_id"], task_id, "task_status", "blocked", reason)
    return updated


def collect_task_outputs(task_id: str) -> list[str]:
    record = get_task_record(task_id) or {}
    outputs = []
    for key in ("stdout_path", "stderr_path"):
        path = Path(record.get(key, ""))
        if path.is_file() and path.stat().st_size:
            outputs.append(str(path))
    manifest = record.get("output_manifest") or {}
    manifest["outputs"] = sorted(set([*manifest.get("outputs", []), *outputs]))
    update_task_record(task_id, output_manifest=manifest)
    return manifest["outputs"]


def validate_task_outputs(task_id: str) -> dict:
    record = get_task_record(task_id) or {}
    spec = _spec_from_record(record)
    root = Path(record.get("working_directory", "."))
    missing = [item for item in spec.get("expected_outputs", []) if not (root / item).exists()]
    return {"status": "passed" if not missing else "failed", "missing": missing}


def cleanup_task(task_id: str) -> dict:
    record = get_task_record(task_id) or {}
    work = Path(record.get("working_directory", ""))
    removed = []
    if work.is_dir():
        for path in work.iterdir():
            if path.is_file():
                path.unlink(); removed.append(str(path))
    return {"status": "passed", "removed": removed}


def get_task_progress(task_id: str) -> dict:
    record = get_task_record(task_id)
    return {"task_id": task_id, "status": record["status"], "progress": record["progress"]} if record else {"task_id": task_id, "status": "missing", "progress": 0}
