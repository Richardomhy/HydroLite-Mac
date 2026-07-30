from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

import pandas as pd

from hydrolite.connectors import get_connector
from hydrolite.data_requirements import build_project_data_requirement_matrix


def select_best_data_source(dataset_type: str, context: dict[str, Any]) -> str:
    preferred = {
        "dem": "gee", "rainfall_forecast": "gee", "temperature": "cds",
        "ICESat2_ATL13": "earthdata", "land_use": "gee", "satellite_image": "stac",
    }
    return preferred.get(dataset_type, "local")


def create_acquisition_plan(workspace_dir: str | Path, workflow_id: str) -> dict[str, Any]:
    matrix = build_project_data_requirement_matrix(workflow_id, workspace_dir)
    steps = []
    for _, row in matrix[matrix["status"] != "ready"].drop_duplicates("dataset_type").iterrows():
        connector = select_best_data_source(row["dataset_type"], {})
        steps.append({
            "step_id": f"acquire_{row['dataset_type']}", "dataset_type": row["dataset_type"], "source": connector,
            "status": "planned", "bbox": None, "start": None, "end": None, "estimated_size_mb": None,
            "license": "check source terms", "login_required": connector in {"gee", "earthdata", "cds"},
            "processing_steps": ["download", "quality_check", "standardize"], "output_format": "source_dependent",
            "user_confirmed": False, "execute": False,
        })
    return {"status": "planned", "workspace_dir": str(Path(workspace_dir).resolve()), "workflow_id": workflow_id, "created_at": datetime.now(timezone.utc).isoformat(), "steps": steps, "download_execute": False}


def estimate_acquisition_cost(plan: dict[str, Any]) -> dict[str, Any]:
    return {"estimated_cost": "unknown_or_free", "requires_user_review": True}


def estimate_acquisition_size(plan: dict[str, Any]) -> dict[str, Any]:
    values = [step["estimated_size_mb"] for step in plan["steps"] if step.get("estimated_size_mb") is not None]
    return {"estimated_size_mb": sum(values) if values else None, "unknown_steps": len(plan["steps"]) - len(values)}


def validate_acquisition_plan(plan: dict[str, Any]) -> dict[str, Any]:
    errors = []
    for step in plan.get("steps", []):
        if step.get("execute") and not step.get("user_confirmed"):
            errors.append(f"{step['step_id']}: execution requires user confirmation")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def execute_acquisition_step(step: dict[str, Any], execute: bool = False) -> dict[str, Any]:
    if not execute:
        return {**step, "status": "dry_run", "download_execute": False}
    if not step.get("user_confirmed"):
        return {**step, "status": "blocked_confirmation_required", "download_execute": False}
    return get_connector(step["source"]).download(step, execute=True)


def execute_acquisition_plan(plan: dict[str, Any], execute: bool = False) -> dict[str, Any]:
    return {"status": "dry_run" if not execute else "completed_with_connector_results", "download_execute": execute, "steps": [execute_acquisition_step(step, execute) for step in plan.get("steps", [])]}


def write_acquisition_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "acquisition_plan.json"
    xlsx_path = output / "acquisition_plan.xlsx"
    md_path = output / "acquisition_report.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    pd.DataFrame(result.get("steps", [])).to_excel(xlsx_path, index=False)
    md_path.write_text(f"# Data Acquisition Plan\n\n- Status: `{result['status']}`\n- Steps: `{len(result.get('steps', []))}`\n- Automatic download: `False`\n", encoding="utf-8")
    return {"json": json_path, "xlsx": xlsx_path, "markdown": md_path}
