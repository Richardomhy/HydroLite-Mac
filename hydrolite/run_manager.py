from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import uuid

import pandas as pd

from hydrolite.__version__ import __version__
from hydrolite.environment_capture import capture_environment, write_environment_snapshot
from hydrolite.project_service import open_project
from hydrolite.run_planner import build_run_plan, validate_run_plan, write_run_plan
from hydrolite.runtime_db import (
    add_task_dependency,
    create_run_record,
    create_runtime_event,
    get_run_record,
    get_task_record,
    list_run_records,
    list_task_records,
    update_run_record,
    update_task_record,
)
from hydrolite.runtime_paths import ensure_runtime_directories, get_run_dir
from hydrolite.task_engine import TERMINAL, cancel_task, create_task, retry_task
from hydrolite.task_models import TaskSpec
from hydrolite.task_queue import enqueue_task, pause_queue, resume_queue


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False, timeout=10).stdout.strip()


def create_run(project_id: str, workflow_id: str, run_config: dict | None = None) -> dict:
    config = run_config or {}
    plan = build_run_plan(project_id, workflow_id, config)
    validation = validate_run_plan(plan)
    if validation["status"] != "passed":
        raise ValueError("; ".join(validation["errors"]))
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    paths = ensure_runtime_directories(run_id)
    config_path = paths["configuration"] / "run_config.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    record = create_run_record(
        run_id=run_id,
        project_id=project_id,
        workflow_id=workflow_id,
        run_name=config.get("run_name") or f"{workflow_id}-{run_id[-6:]}",
        run_mode=plan["run_mode"],
        status="created",
        progress=0,
        current_stage="",
        configuration_path=str(config_path),
        configuration_checksum=hashlib.sha256(config_path.read_bytes()).hexdigest(),
        git_commit=_git_commit(),
        hydrolite_version=__version__,
        python_version=sys.version,
        warnings=[],
    )
    task_map = {}
    for planned in plan["tasks"]:
        spec_values = {key: value for key, value in planned.items() if key not in {"task_id", "dependencies"}}
        spec_values["dependencies"] = []
        task = create_task(spec_values, run_id)
        task_map[planned["task_id"]] = task["task_id"]
    for planned in plan["tasks"]:
        child = task_map[planned["task_id"]]
        for dependency in planned.get("dependencies", []):
            add_task_dependency(child, task_map[dependency["task_id"]], bool(dependency.get("required", True)))
    plan["run_id"] = run_id
    plan["task_id_map"] = task_map
    write_run_plan(run_id, paths["configuration"] / "run_plan.json", plan)
    (paths["run"] / "run_manifest.json").write_text(json.dumps({"run": record, "plan": plan}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    create_runtime_event(run_id, None, "run_created", "created")
    return record


def prepare_run(run_id: str) -> dict:
    record = get_run_record(run_id)
    if not record: raise KeyError(run_id)
    update_run_record(run_id, status="validating")
    project = open_project(record["project_id"])
    workspace = Path(project["workspace_path"])
    paths = ensure_runtime_directories(run_id)
    input_manifest = {}
    for name in ("project.yaml", "workspace_manifest.json"):
        source = workspace / name
        if source.exists():
            target = paths["configuration"] / name
            shutil.copy2(source, target)
            input_manifest[name] = {"checksum": hashlib.sha256(target.read_bytes()).hexdigest(), "source_name": source.name}
    (paths["configuration"] / "input_checksums.json").write_text(json.dumps(input_manifest, indent=2), encoding="utf-8")
    environment = capture_environment()
    write_environment_snapshot(paths["environments"] / environment["environment_id"], environment)
    return update_run_record(run_id, status="ready", environment_id=environment["environment_id"])


def start_run(run_id: str) -> dict:
    record = get_run_record(run_id)
    if not record: raise KeyError(run_id)
    if record["status"] == "created":
        prepare_run(run_id)
    for task in reversed(list_task_records(run_id=run_id)):
        if task["status"] in {"pending", "retrying"}:
            enqueue_task(task["task_id"])
    create_runtime_event(run_id, None, "run_status", "queued")
    return update_run_record(run_id, status="queued", started_at=record.get("started_at") or _now())


def pause_run(run_id: str) -> dict:
    pause_queue()
    return update_run_record(run_id, status="paused")


def resume_run(run_id: str) -> dict:
    resume_queue()
    return update_run_record(run_id, status="queued")


def cancel_run(run_id: str) -> dict:
    for task in list_task_records(run_id=run_id):
        if task["status"] not in TERMINAL:
            cancel_task(task["task_id"])
    return update_run_record(run_id, status="cancelled", finished_at=_now(), result_status="cancelled")


def retry_failed_run(run_id: str) -> dict:
    retried = []
    for task in list_task_records(run_id=run_id):
        if task["status"] in {"failed", "timed_out", "cancelled"}:
            result = retry_task(task["task_id"])
            if result.get("status") == "retrying":
                retried.append(task["task_id"])
    if retried:
        update_run_record(run_id, status="queued", finished_at=None, result_status="")
    return {"run_id": run_id, "retried": retried}


def retry_from_stage(run_id: str, stage_id: str) -> dict:
    tasks = list(reversed(list_task_records(run_id=run_id)))
    found, reset = False, []
    for task in tasks:
        if task["stage_id"] == stage_id: found = True
        if found:
            update_task_record(task["task_id"], status="queued", return_code=None, error_type="", error_message="", cancelled_by_user=False)
            reset.append(task["task_id"])
    if not found: raise KeyError(f"Stage not found: {stage_id}")
    update_run_record(run_id, status="queued", finished_at=None)
    return {"run_id": run_id, "stage_id": stage_id, "reset_tasks": reset}


def clone_run(run_id: str, new_config: dict | None = None) -> dict:
    record = get_run_record(run_id)
    if not record: raise KeyError(run_id)
    return create_run(record["project_id"], record["workflow_id"], new_config)


def calculate_run_progress(run_id: str) -> dict:
    tasks = list_task_records(run_id=run_id)
    complete = sum(task["status"] in TERMINAL for task in tasks)
    progress = 100 * complete / len(tasks) if tasks else 0
    current = next((task["stage_id"] for task in reversed(tasks) if task["status"] == "running"), "")
    update_run_record(run_id, progress=progress, current_stage=current)
    counts = {status: sum(task["status"] == status for task in tasks) for status in sorted({task["status"] for task in tasks})}
    return {"run_id": run_id, "progress": progress, "task_count": len(tasks), "counts": counts, "current_stage": current}


def inspect_run(run_id: str) -> dict:
    record = get_run_record(run_id)
    if not record: raise KeyError(run_id)
    return {"run": record, "progress": calculate_run_progress(run_id), "tasks": list(reversed(list_task_records(run_id=run_id)))}


def finalize_run(run_id: str) -> dict:
    tasks = list(reversed(list_task_records(run_id=run_id)))
    if not tasks: return update_run_record(run_id, status="failed", error_summary="Run has no tasks.")
    required_failed, optional_failed = [], []
    for task in tasks:
        spec = task.get("command") if isinstance(task.get("command"), dict) else {}
        if task["status"] in {"failed", "timed_out", "cancelled", "blocked"}:
            (optional_failed if spec.get("optional") else required_failed).append(task)
    if required_failed:
        status = "failed"
    elif optional_failed:
        status = "succeeded_with_warnings"
    elif all(task["status"] in {"succeeded", "succeeded_with_warnings", "skipped"} for task in tasks):
        status = "succeeded"
    else:
        status = "partially_succeeded"
    update_run_record(run_id, status=status, progress=100, finished_at=_now(), result_status=status, warnings=[task["error_message"] for task in optional_failed], error_summary="; ".join(task["error_message"] for task in required_failed))
    create_runtime_event(run_id, None, "run_status", status)
    write_run_reports(run_id)
    from hydrolite.artifact_store import discover_run_artifacts
    discover_run_artifacts(run_id)
    return get_run_record(run_id) or {}


def validate_run(run_id: str) -> dict:
    run = get_run_record(run_id)
    tasks = list_task_records(run_id=run_id)
    required_bad = []
    for task in tasks:
        spec = task.get("command") if isinstance(task.get("command"), dict) else {}
        if not spec.get("optional") and task["status"] not in {"succeeded", "succeeded_with_warnings", "skipped"}:
            required_bad.append(task["task_id"])
    return {"status": "passed" if run and not required_bad and run["status"] in {"succeeded", "succeeded_with_warnings"} else "failed", "run_id": run_id, "required_task_failures": required_bad}


def archive_run(run_id: str) -> dict:
    return update_run_record(run_id, status="archived")


def export_run_manifest(run_id: str, output_path: str | Path) -> Path:
    target = Path(output_path); target.parent.mkdir(parents=True, exist_ok=True)
    payload = inspect_run(run_id)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return target


def write_run_reports(run_id: str) -> dict[str, Path]:
    paths = ensure_runtime_directories(run_id)
    details = inspect_run(run_id)
    run, tasks = details["run"], details["tasks"]
    summary = paths["reports"] / "run_summary.xlsx"
    errors = [task for task in tasks if task["status"] in {"failed", "timed_out", "cancelled", "blocked"}]
    warnings = [task for task in tasks if (task.get("command") or {}).get("optional") and task["status"] == "failed"]
    with pd.ExcelWriter(summary) as writer:
        pd.DataFrame([run]).to_excel(writer, sheet_name="run", index=False)
        pd.DataFrame(tasks).to_excel(writer, sheet_name="tasks", index=False)
    pd.DataFrame(errors).to_excel(paths["reports"] / "run_errors.xlsx", index=False)
    pd.DataFrame(warnings).to_excel(paths["reports"] / "run_warnings.xlsx", index=False)
    zh = paths["reports"] / "run_report_zh.md"
    en = paths["reports"] / "run_report_en.md"
    zh.write_text(f"# 运行报告\n\n- Run ID：`{run_id}`\n- 工作流：`{run['workflow_id']}`\n- 状态：`{run['status']}`\n- 任务数：`{len(tasks)}`\n- 失败任务：`{len(errors)}`\n", encoding="utf-8")
    en.write_text(f"# Run Report\n\n- Run ID: `{run_id}`\n- Workflow: `{run['workflow_id']}`\n- Status: `{run['status']}`\n- Tasks: `{len(tasks)}`\n- Failed tasks: `{len(errors)}`\n", encoding="utf-8")
    manifest = paths["run"] / "run_manifest.json"
    manifest.write_text(json.dumps(details, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {"summary": summary, "report_zh": zh, "report_en": en, "errors": paths["reports"] / "run_errors.xlsx", "warnings": paths["reports"] / "run_warnings.xlsx", "manifest": manifest}
