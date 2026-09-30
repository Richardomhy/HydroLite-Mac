from __future__ import annotations

from copy import deepcopy


_RECIPES = {
    "water_environment_evidence_closure": {
        "name_zh": "污染源证据补全", "name_en": "Source evidence closure",
        "stages": ["source_evidence_completion", "artifact_management", "reporting"],
        "command": "python -m hydrolite water-environment evidence",
        "local_only_tasks": ["source_evidence_completion"],
        "expected_outputs": ["m9a1_manifest.json", "m9b_readiness.xlsx", "m9a1_data_request_list.xlsx"],
        "limitations": ["No mobilization, transport, concentrations or automatic factor approval"],
    },
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
    "real_project_baseline_audit": {
        "name_zh": "真实项目基线审计",
        "name_en": "Real project baseline audit",
        "use_case": "只读盘点真实资料并形成数据质量、能力就绪度、验证边界和产品摩擦证据。",
        "required_data": ["external real project source"],
        "optional_data": ["observed flow", "water-quality observations", "spatial data"],
        "stages": ["real_project_baseline", "artifact_management", "reporting"],
        "expected_outputs": ["real_project_data_inventory.xlsx", "capability_readiness.xlsx", "m8a_real_project_manifest.json"],
        "local_only_tasks": ["real_project_baseline"],
        "estimated_complexity": "medium",
        "limitations": ["不复制真实资料，不运行未就绪模型，不构成独立验证。"],
    },
    "real_project_model_validation": {
        "name_zh": "真实项目 HydroLite 诊断闭环",
        "name_en": "Real-project HydroLite diagnostic closure",
        "use_case": "在 M8A 基线上生成可追溯输入，执行真实 HydroLite Run，并开展水量平衡、事件诊断和 what-if 情景对比。",
        "required_data": ["M8A workspace", "reviewed basin inputs", "rainfall", "observed flow"],
        "optional_data": ["wet-weather water-quality observations"],
        "stages": ["real_project_model_validation", "artifact_management", "reporting"],
        "expected_outputs": ["hydrolite_real_run_manifest.json", "event_metrics.xlsx", "scenario_comparison.xlsx", "m8b_manifest.json"],
        "local_only_tasks": ["real_project_model_validation"],
        "estimated_complexity": "medium",
        "validation_level": "real_data_diagnostic",
        "limitations": ["不构成独立水文验证；情景仅为 what-if；water_quality 仍为 planned；M9 未实施。"],
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
    "continuous_model_diagnosis": {"stages": ["continuous_input_audit", "pet_validation", "continuous_balance_audit", "continuous_structure_diagnostic", "reporting"]},
    "synthetic_truth_recovery": {"stages": ["synthetic_truth_recovery", "parameter_application_audit", "reporting"]},
    "continuous_staged_calibration": {"stages": ["continuous_sensitivity", "continuous_benchmarking", "staged_continuous_calibration", "reporting"]},
    "drought_consistency_audit": {"stages": ["drought_consistency_audit", "reporting"]},
    "water_quality_hydrology_preflight": {"stages": ["water_quality_hydrology_gate", "reporting"]},
    "water_environment_source_accounting": {
        "name_zh": "水环境污染源与负荷账本",
        "name_en": "Water environment source accounting",
        "use_case": "建立污染源清单、活动量、系数、处理削减与净排放负荷账本。",
        "required_data": ["pollution_source_inventory"],
        "optional_data": ["source_activity", "emission_factor", "treatment_factor"],
        "stages": ["pollution_source_inventory", "source_load_accounting", "reporting"],
        "expected_outputs": ["pollution_source_inventory.xlsx", "source_load_ledger.xlsx", "coverage_summary.xlsx", "m9a_manifest.json"],
        "local_only_tasks": ["pollution_source_inventory", "source_load_accounting"],
        "estimated_complexity": "medium",
        "validation_level": "source_accounting_only",
        "limitations": ["不计算污染物动员、输移、河道过程或断面浓度。"],
    },
    "hindcast_validation_full": {"stages": ["event_catalog", "observation_quality_control", "observation_mapping", "event_split", "multi_event_hindcast", "multi_event_calibration", "data_assimilation", "lead_time_validation", "model_validation", "reporting"], "local_only_tasks": ["hec_hms_run"]},
    "reservoir_analysis": {"stages": ["hydrology", "reservoir_routing", "reporting"]},
    "erosion_sediment": {"stages": ["rusle", "sediment_delivery", "reporting"]},
    "conservation_accounting": {"stages": ["conservation", "watershed_accounting", "reporting"]},
    "full_modeling_workflow": {"stages": ["data_center", "data_standardization", "watershed_delineation", "hydrology", "water_balance_audit", "hec_hms_project", "reservoir_routing", "flood_forecast", "rusle", "sediment_delivery", "watershed_accounting", "reporting"], "local_only_tasks": ["hec_hms_run"]},
    "reporting_only": {"stages": ["reporting"]},
    "gee_dataset_discovery": {"stages": ["gee_catalog_intelligence", "reporting"], "expected_outputs": ["gee_catalog_report_zh.md"]},
    "data_requirement_resolution": {"stages": ["resolve_data_requirements", "reporting"], "expected_outputs": ["resolution_manifest.json", "user_required_data.xlsx"]},
    "public_data_acquisition": {"stages": ["resolve_data_requirements", "fetch_public_data", "data_standardization", "reporting"], "expected_outputs": ["workspace_manifest.json", "lineage_manifest.json"]},
    "research_method_intake": {"stages": ["research_source_intake", "research_license_review", "method_inspiration_lab"], "expected_outputs": ["research_sources.xlsx", "research_methods.xlsx"]},
    "gamma_lag_experiment": {"stages": ["gamma_lag_features"], "expected_outputs": ["kernels/single_kernel.csv", "features/gamma_features.csv", "reports/gamma_lag_manifest.json"]},
    "graph_hydrology_experiment": {"stages": ["river_graph_features", "trend_aware_features", "multihorizon_forecast"], "expected_outputs": ["graph/graph_manifest.json", "forecast/horizon_metrics.xlsx", "reports/graph_trend_manifest.json"]},
    "water_quality_multistation_experiment": {
        "stages": ["water_quality_qc", "station_mapping", "concentration_load", "causal_features", "multihorizon_forecast", "feature_ablation", "validation", "report"],
        "expected_outputs": ["forecast/station_predictions.csv", "forecast/horizon_metrics.xlsx", "reports/water_quality_method_report_zh.md"],
        "command": "python -m hydrolite water-quality-lab demo",
        "validation_level": "synthetic_method_demo",
    },
    "water_quality_multihorizon_experiment": {"stages": ["water_quality_method_lab", "hierarchical_multihorizon"], "expected_outputs": ["multihorizon_metrics.xlsx"], "deprecated_by": "water_quality_multistation_experiment"},
    "flood_susceptibility_mapping": {
        "stages": ["flood_susceptibility", "flood_susceptibility_xai"],
        "expected_outputs": ["models/model_metrics.xlsx", "mapping/susceptibility_map.geojson", "xai/global_importance.xlsx", "reports/flood_susceptibility_report_zh.md"],
        "command": "python -m hydrolite susceptibility demo",
        "validation_level": "synthetic_spatial_demo",
        "limitations": ["易发性不等于风险；synthetic demo 不等于真实验证；RL 未实现。"],
    },
    "flood_susceptibility_xai": {"stages": ["flood_susceptibility", "flood_susceptibility_xai"], "expected_outputs": ["xai/global_importance.xlsx"], "deprecated_by": "flood_susceptibility_mapping"},
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
