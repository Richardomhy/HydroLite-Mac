from __future__ import annotations

from pathlib import Path
import json
import sys

from hydrolite.project_service import open_project
from hydrolite.run_recipes import get_run_recipe
from hydrolite.runtime_mode import detect_runtime_mode, validate_task_for_mode
from hydrolite.task_models import TaskDependency, TaskSpec


def convert_workflow_stage_to_tasks(stage: str, context: dict) -> list[TaskSpec]:
    project_root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "hydrolite", "version"]
    optional = stage == "demo_optional_probe"
    if optional:
        command = [sys.executable, "-c", "import sys; print('expected optional failure'); sys.exit(2)"]
    local_only = stage in {"hec_hms_run", "qgis_preprocessing", "watershed_delineation"}
    task = TaskSpec(
        stage_id=stage,
        display_name=stage.replace("_", " ").title(),
        command=command,
        environment={"PYTHONPATH": str(project_root)},
        timeout=int(context.get("task_timeout", 120)),
        expected_outputs=[],
        optional=optional,
        local_only=local_only,
        cloud_supported=not local_only,
    )
    return [task]


def build_run_plan(project_id: str, workflow_id: str, run_config: dict | None = None) -> dict:
    config = run_config or {}
    project = open_project(project_id)
    recipe = get_run_recipe(workflow_id)
    tasks = []
    previous = None
    previous_optional = False
    for stage in recipe["stages"]:
        for task in convert_workflow_stage_to_tasks(stage, config):
            if previous:
                task.dependencies = [TaskDependency(previous, required=not previous_optional)]
            task_id = f"task_{len(tasks)+1:03d}_{stage}"
            tasks.append({"task_id": task_id, **task.as_dict()})
            previous = task_id
            previous_optional = task.optional
    plan = {
        "project_id": project_id,
        "project_name": project["display_name"],
        "workflow_id": workflow_id,
        "run_mode": config.get("run_mode") or detect_runtime_mode()["mode"],
        "workspace_path": project["workspace_path"],
        "tasks": tasks,
        "estimated_task_count": len(tasks),
        "estimated_storage_mb": sum(task["resource_limits"]["estimated_storage_mb"] for task in tasks),
    }
    plan["blocked_tasks"] = identify_blocked_tasks(plan)
    return plan


def resolve_run_dependencies(plan: dict) -> dict:
    known = {task["task_id"] for task in plan["tasks"]}
    missing = [dep["task_id"] for task in plan["tasks"] for dep in task["dependencies"] if dep["task_id"] not in known]
    return {"status": "passed" if not missing else "failed", "missing_dependencies": missing}


def validate_run_plan(plan: dict) -> dict:
    errors = []
    if not plan.get("tasks"): errors.append("Run plan has no tasks.")
    dependency = resolve_run_dependencies(plan)
    errors.extend(f"Missing dependency: {item}" for item in dependency["missing_dependencies"])
    return {"status": "passed" if not errors else "failed", "errors": errors}


def estimate_run_plan(plan: dict) -> dict:
    return {"task_count": len(plan.get("tasks", [])), "estimated_storage_mb": plan.get("estimated_storage_mb", 0), "complexity": "light" if len(plan.get("tasks", [])) <= 5 else "medium"}


def write_run_plan(run_id: str, output_path: str | Path, plan: dict | None = None) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan or {"run_id": run_id}, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def generate_run_summary(plan: dict) -> str:
    return f"{plan['workflow_id']}: {len(plan['tasks'])} tasks, {len(plan.get('blocked_tasks', []))} blocked."


def identify_local_only_tasks(plan: dict) -> list[str]:
    return [task["task_id"] for task in plan.get("tasks", []) if task.get("local_only")]


def identify_blocked_tasks(plan: dict) -> list[dict]:
    mode = detect_runtime_mode(plan.get("run_mode"))
    return [{"task_id": task["task_id"], **result} for task in plan.get("tasks", []) if (result := validate_task_for_mode(task, mode))["status"] == "blocked"]
