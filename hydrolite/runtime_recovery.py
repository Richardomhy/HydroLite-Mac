from __future__ import annotations

from pathlib import Path
import json

from hydrolite.runtime_db import get_run_record, list_run_records, list_task_records, update_run_record, update_task_record
from hydrolite.task_engine import retry_task
from hydrolite.task_queue import recover_interrupted_tasks


FAILURE_GUIDANCE = {
    "invalid_input": ("输入格式或字段无效。", False, "修正输入并从当前阶段重试。"),
    "missing_input": ("缺少必需输入。", False, "补充缺失数据后重试。"),
    "data_quality_failed": ("数据质量门禁未通过。", False, "在数据中心修复问题。"),
    "dependency_missing": ("缺少运行依赖。", False, "在隔离环境安装依赖。"),
    "authentication_required": ("外部平台需要认证。", False, "在本地完成认证，不提交凭证。"),
    "local_backend_unavailable": ("本地后端不可用。", False, "切换轻量模式或修复后端。"),
    "external_backend_failed": ("外部后端执行失败。", True, "检查日志后重试一次。"),
    "timeout": ("任务超时。", True, "调整 timeout 或缩小任务范围。"),
    "cancelled": ("任务已由用户取消。", True, "确认后重新入队。"),
    "numerical_instability": ("模型数值稳定性检查失败。", False, "调整参数或时间步长。"),
    "model_validation_failed": ("模型输出校验失败。", False, "检查模型配置和必需输出。"),
    "output_missing": ("缺少预期成果。", True, "检查任务日志并重试。"),
    "output_invalid": ("成果未通过最低质量校验。", False, "修复生成步骤。"),
    "permission_error": ("目录权限不足。", False, "选择可写目录。"),
    "disk_space_error": ("磁盘空间不足。", False, "释放空间或更换运行目录。"),
    "internal_error": ("HydroLite 内部错误。", True, "保存日志并提交问题。"),
    "unknown": ("未知错误。", False, "查看技术日志。"),
}


def classify_task_failure(task_result) -> str:
    status = task_result.get("status") if isinstance(task_result, dict) else getattr(task_result, "status", "")
    message = str(task_result.get("error_message", "") if isinstance(task_result, dict) else getattr(task_result, "errors", "")).lower()
    if status == "timed_out": return "timeout"
    if status == "cancelled": return "cancelled"
    if "permission" in message: return "permission_error"
    if "no space" in message or "disk" in message: return "disk_space_error"
    if "missing" in message or "not found" in message: return "missing_input"
    if "auth" in message: return "authentication_required"
    if "stability" in message or "numerical" in message: return "numerical_instability"
    return "external_backend_failed" if status == "failed" else "unknown"


def determine_retryability(task_result) -> dict:
    category = classify_task_failure(task_result)
    user, retryable, action = FAILURE_GUIDANCE[category]
    return {"failure_type": category, "retryable": retryable, "user_message": user, "technical_message": str(task_result), "suggested_action": action, "resume_from_stage": retryable}


def build_recovery_plan(run_id: str) -> dict:
    tasks = list(reversed(list_task_records(run_id=run_id)))
    actions = []
    for task in tasks:
        if task["status"] in {"failed", "timed_out", "cancelled", "interrupted"}:
            guidance = determine_retryability(task)
            actions.append({"task_id": task["task_id"], "stage_id": task["stage_id"], **guidance})
    return {"run_id": run_id, "status": "recoverable" if any(row["retryable"] for row in actions) else "manual_action_required", "actions": actions}


def recover_interrupted_run(run_id: str) -> dict:
    run = get_run_record(run_id)
    if not run: raise KeyError(run_id)
    recovered = []
    for task in list_task_records(run_id=run_id):
        if task["status"] in {"running", "interrupted"}:
            update_task_record(task["task_id"], status="failed", error_type="internal_error", error_message="Interrupted task requires explicit retry.", retryable=True)
            recovered.append(task["task_id"])
    update_run_record(run_id, status="interrupted", error_summary="Run was interrupted; completed artifacts were retained.")
    return {"status": "passed", "run_id": run_id, "recovered_tasks": recovered}


def retry_failed_tasks(run_id: str) -> dict:
    retried = []
    for task in list_task_records(run_id=run_id):
        if task["status"] in {"failed", "timed_out", "cancelled"} and determine_retryability(task)["retryable"]:
            result = retry_task(task["task_id"])
            if result.get("status") == "retrying": retried.append(task["task_id"])
    return {"run_id": run_id, "retried": retried}


def resume_from_checkpoint(run_id: str) -> dict:
    return recover_interrupted_run(run_id)


def validate_recovery_result(run_id: str) -> dict:
    tasks = list_task_records(run_id=run_id)
    bad = [task["task_id"] for task in tasks if task["status"] == "running"]
    return {"status": "passed" if not bad else "failed", "still_running": bad}


def write_recovery_report(output_dir: str | Path, result: dict) -> Path:
    path = Path(output_dir) / "recovery_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def recover_all_runtime() -> dict:
    interrupted_tasks = recover_interrupted_tasks()
    runs = []
    for run in list_run_records():
        if run["status"] in {"running", "queued", "validating"}:
            runs.append(recover_interrupted_run(run["run_id"]))
    return {"status": "passed", "tasks": interrupted_tasks, "runs": runs}
