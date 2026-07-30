from __future__ import annotations

from copy import deepcopy


_RECIPES = {
    "data_preparation": {
        "name_zh": "数据准备",
        "name_en": "Data preparation",
        "use_case": "注册工作区、检查数据并生成轻量运行报告。",
        "required_data": ["project.yaml", "workspace_manifest.json"],
        "optional_data": [],
        "stages": ["environment_capture", "workspace_validation", "demo_optional_probe", "reporting"],
        "expected_outputs": ["environment_snapshot.json", "run_report_zh.md"],
        "local_only_tasks": [],
        "estimated_complexity": "light",
        "limitations": ["不执行外部下载或重型模型。"],
    },
    "watershed_hydrology": {"stages": ["data_standardization", "watershed_delineation", "hydrology", "water_balance_audit", "reporting"]},
    "hydrology_hec_hms_compare": {"stages": ["hydrology", "hec_hms_project", "hec_hms_run", "reporting"], "local_only_tasks": ["hec_hms_run"]},
    "flood_hindcast": {"stages": ["hydrology", "flood_forecast", "reporting"]},
    "multi_event_hindcast": {"stages": ["event_catalog", "observation_quality_control", "observation_mapping", "event_split", "multi_event_hindcast", "model_validation", "reporting"]},
    "multi_event_calibration": {"stages": ["event_catalog", "event_split", "multi_event_hindcast", "multi_event_calibration", "model_validation", "reporting"]},
    "flow_data_assimilation": {"stages": ["multi_event_hindcast", "data_assimilation", "lead_time_validation", "model_validation", "reporting"]},
    "continuous_water_balance": {"stages": ["continuous_hydrology", "evapotranspiration", "soil_water_balance", "groundwater_baseflow", "drought_model_validation", "reporting"]},
    "historical_drought_analysis": {"stages": ["continuous_hydrology", "drought_indices", "drought_event_catalog", "drought_model_validation", "reporting"]},
    "current_drought_monitoring": {"stages": ["continuous_hydrology", "drought_indices", "drought_monitoring", "reporting"]},
    "drought_scenario_forecast": {"stages": ["continuous_hydrology", "drought_scenarios", "drought_forecast", "drought_model_validation", "reporting"]},
    "drought_data_assimilation": {"stages": ["continuous_hydrology", "drought_data_assimilation", "drought_forecast", "reporting"]},
    "drought_full_workflow": {"stages": ["continuous_hydrology", "evapotranspiration", "soil_water_balance", "groundwater_baseflow", "drought_indices", "drought_event_catalog", "drought_monitoring", "drought_scenarios", "drought_forecast", "drought_data_assimilation", "drought_model_validation", "reporting"]},
    "hindcast_validation_full": {"stages": ["event_catalog", "observation_quality_control", "observation_mapping", "event_split", "multi_event_hindcast", "multi_event_calibration", "data_assimilation", "lead_time_validation", "model_validation", "reporting"], "local_only_tasks": ["hec_hms_run"]},
    "reservoir_analysis": {"stages": ["hydrology", "reservoir_routing", "reporting"]},
    "erosion_sediment": {"stages": ["rusle", "sediment_delivery", "reporting"]},
    "conservation_accounting": {"stages": ["conservation", "watershed_accounting", "reporting"]},
    "full_modeling_workflow": {"stages": ["data_center", "data_standardization", "watershed_delineation", "hydrology", "water_balance_audit", "hec_hms_project", "reservoir_routing", "flood_forecast", "rusle", "sediment_delivery", "watershed_accounting", "reporting"], "local_only_tasks": ["hec_hms_run"]},
    "reporting_only": {"stages": ["reporting"]},
}


def list_run_recipes() -> list[dict]:
    return [{"recipe_id": key, **value} for key, value in _RECIPES.items()]


def get_run_recipe(recipe_id: str) -> dict:
    if recipe_id not in _RECIPES:
        raise KeyError(f"Unknown run recipe: {recipe_id}")
    base = {
        "recipe_id": recipe_id,
        "name_zh": recipe_id,
        "name_en": recipe_id.replace("_", " ").title(),
        "use_case": "",
        "required_data": [],
        "optional_data": [],
        "stages": [],
        "expected_outputs": [],
        "local_only_tasks": [],
        "estimated_complexity": "medium",
        "limitations": [],
    }
    base.update(deepcopy(_RECIPES[recipe_id]))
    return base


def copy_run_recipe(recipe_id: str) -> dict:
    return get_run_recipe(recipe_id)
