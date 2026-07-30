from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from hydrolite.workspace import list_workspace_datasets


_MODEL_REQUIREMENTS = {
    "hydrolite_event_model": [("rainfall_observed", True), ("subbasins", True), ("reaches", True), ("streamflow_observed", False)],
    "hec_hms_event_model": [("rainfall_observed", True), ("subbasins", True), ("reaches", True), ("watershed_boundary", False)],
    "swmm": [("swmm_inp", True), ("rainfall_observed", False)],
    "watershed_delineation": [("dem", True), ("outlet_points", True), ("watershed_boundary", False)],
    "flood_forecast": [("rainfall_forecast", True), ("rainfall_observed", False), ("streamflow_observed", False), ("reservoir_level", False)],
    "multi_event_hindcast": [("rainfall_observed", True), ("streamflow_observed", True), ("flood_event_catalog", True), ("subbasins", True), ("reaches", True), ("water_level_observed", False), ("data_assimilation_observations", False)],
    "drought_forecast": [("rainfall_observed", True), ("temperature", False), ("streamflow_observed", False)],
    "icesat2": [("waterbody_boundary", True), ("ICESat2_ATL13", False)],
    "rusle": [("dem", True), ("RUSLE_R", True), ("RUSLE_K", True), ("RUSLE_C", True), ("RUSLE_P", True)],
    "sediment_delivery": [("RUSLE_R", True), ("sediment_observations", False)],
    "reservoir_routing": [("stage_area_volume", True), ("stage_discharge", True), ("reservoir_level", False)],
    "conservation": [("subbasins", True), ("land_use", False), ("soil_properties", False)],
    "watershed_accounting": [("rainfall_observed", True), ("streamflow_observed", False), ("sediment_observations", False)],
    "water_quality": [("water_quality_observations", True), ("pollutant_sources", False), ("streamflow_observed", True)],
}
_SYSTEM = {"dem": ["GEE", "Earthdata", "STAC"], "rainfall_forecast": ["GEE", "CDS"], "temperature": ["GEE", "CDS"], "ICESat2_ATL13": ["Earthdata"], "RUSLE_R": ["GEE"], "land_use": ["GEE", "STAC"]}


def list_model_data_requirements(model_id: str) -> list[dict[str, Any]]:
    return [{"model_id": model_id, "dataset_type": dataset_type, "required": required, "default_status": "system_retrievable" if dataset_type in _SYSTEM else ("user_upload_required" if required else "optional_user_upload"), "sources": _SYSTEM.get(dataset_type, ["local"])} for dataset_type, required in _MODEL_REQUIREMENTS.get(model_id, [])]


def assess_model_data_readiness(model_id: str, workspace_dir: str | Path) -> dict[str, Any]:
    datasets = list_workspace_datasets(workspace_dir)
    ready_types = {item.get("user_declared_type") or item.get("classification", {}).get("dataset_type") for item in datasets if item.get("quality_status") in {"ready", "ready_with_warnings"}}
    rows = []
    for row in list_model_data_requirements(model_id):
        status = "ready" if row["dataset_type"] in ready_types else row["default_status"]
        rows.append({**row, "status": status})
    missing = [row["dataset_type"] for row in rows if row["required"] and row["status"] != "ready"]
    return {"model_id": model_id, "status": "ready" if not missing else "incomplete", "requirements": rows, "missing_required": missing}


def build_project_data_requirement_matrix(workflow_id: str, workspace_dir: str | Path) -> pd.DataFrame:
    models = list(_MODEL_REQUIREMENTS) if workflow_id == "full_modeling_workflow" else [workflow_id]
    rows = [row for model in models for row in assess_model_data_readiness(model, workspace_dir)["requirements"]]
    return pd.DataFrame(rows)


def find_missing_required_datasets(matrix: pd.DataFrame) -> pd.DataFrame:
    return matrix[(matrix["required"]) & (matrix["status"] != "ready")].copy()


def find_optional_datasets(matrix: pd.DataFrame) -> pd.DataFrame:
    return matrix[~matrix["required"]].copy()


def find_auto_retrievable_datasets(matrix: pd.DataFrame) -> pd.DataFrame:
    return matrix[matrix["status"] == "system_retrievable"].copy()


def recommend_data_sources(matrix: pd.DataFrame) -> pd.DataFrame:
    result = matrix.copy()
    result["recommended_source"] = result["sources"].apply(lambda value: value[0] if isinstance(value, list) and value else "local")
    return result


def write_data_readiness_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    matrix = result["matrix"]
    requirements = output / "project_data_requirements.xlsx"
    readiness = output / "model_data_readiness.xlsx"
    actions = output / "missing_data_actions.xlsx"
    matrix.to_excel(requirements, index=False)
    overview = matrix.groupby("model_id").apply(lambda group: pd.Series({"ready": int((group["status"] == "ready").sum()), "missing_required": int(((group["required"]) & (group["status"] != "ready")).sum())}), include_groups=False).reset_index()
    overview.to_excel(readiness, index=False)
    recommend_data_sources(find_missing_required_datasets(matrix)).to_excel(actions, index=False)
    zh, en = output / "data_readiness_report_zh.md", output / "data_readiness_report_en.md"
    zh.write_text(f"# 数据就绪度\n\n- 工作流：`{result['workflow_id']}`\n- 缺少必需数据：`{len(find_missing_required_datasets(matrix))}`\n", encoding="utf-8")
    en.write_text(f"# Data Readiness\n\n- Workflow: `{result['workflow_id']}`\n- Missing required datasets: `{len(find_missing_required_datasets(matrix))}`\n", encoding="utf-8")
    return {"requirements": requirements, "readiness": readiness, "actions": actions, "zh": zh, "en": en}
