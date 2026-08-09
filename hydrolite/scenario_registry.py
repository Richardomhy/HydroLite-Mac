"""Scenario-driven product entry points backed by the existing workflow engine."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from hydrolite.run_recipes import get_run_recipe
from hydrolite.scenario_contracts import ScenarioDefinition, ScenarioReadiness, validate_scenario_definition


def _scenario(
    scenario_id: str, zh: str, en: str, question: str, required: tuple[str, ...],
    optional: tuple[str, ...], capabilities: tuple[str, ...], workflow: str,
    outputs: tuple[str, ...], validation: str, status: str, limitations: tuple[str, ...],
    *, automatic: tuple[str, ...] = (), recommended: tuple[str, ...] = (),
    not_recommended: tuple[str, ...] = (), advanced: bool = False,
) -> ScenarioDefinition:
    return ScenarioDefinition(
        scenario_id, zh, en, question, question, required, optional, automatic,
        capabilities, workflow, {"required_must_be_available": True}, outputs,
        validation, status, limitations, recommended, not_recommended, advanced,
    )


_SCENARIOS = (
    _scenario("SC01", "历史洪水复盘", "Historical Flood Analysis", "历史洪水过程表现如何，误差来自哪里？", ("rainfall", "observed_streamflow", "subbasins", "reaches"), ("initial_state", "hec_hms_project"), ("historical_flood_validation", "hydrology"), "hindcast_validation_full", ("timeseries", "metrics", "comparison", "report"), "ready_with_warnings", "ready_with_warnings", ("真实事件质量和初始状态决定结论可信度。",), recommended=("历史事件复盘", "多模型验证")),
    _scenario("SC02", "洪水预测与情景分析", "Flood Forecast", "未来降雨情景下可能出现怎样的洪水过程？", ("forecast_rainfall", "subbasins", "reaches"), ("observed_streamflow", "reservoir_state"), ("flood_forecast", "hydrology"), "flood_hindcast", ("timeseries", "uncertainty", "report"), "ready_with_warnings", "ready_with_warnings", ("能力为 partial，不构成业务化预警系统。",), recommended=("情景比较",), not_recommended=("实时预警发布",)),
    _scenario("SC03", "干旱监测与情景分析", "Drought Monitoring", "当前干旱状态及未来情景如何？", ("continuous_meteorology",), ("soil_moisture", "reservoir_storage"), ("drought_monitoring", "drought_forecast"), "current_drought_monitoring", ("timeseries", "metrics", "diagnostic", "report"), "ready_with_warnings", "ready_with_warnings", ("干旱预测仍为 partial。",), recommended=("历史监测", "情景分析")),
    _scenario("SC04", "水库调蓄分析", "Reservoir Routing", "水库对入流洪水的削峰与错峰作用如何？", ("reservoir_curve", "inflow_timeseries"), ("observed_level", "release_rule"), ("reservoir_routing",), "reservoir_analysis", ("timeseries", "metrics", "table", "report"), "ready_with_warnings", "ready_with_warnings", ("工程应用需核验库容曲线和调度规则。",), recommended=("调蓄情景比较",)),
    _scenario("SC05", "流域水文模拟", "Watershed Hydrology", "降雨如何转化为流域出口径流？", ("rainfall", "subbasins", "reaches"), ("observed_streamflow",), ("hydrology",), "watershed_hydrology", ("timeseries", "metrics", "table", "report"), "production_ready", "production_ready", ("正式应用仍需项目数据校验和率定。",), recommended=("事件产汇流", "水量平衡")),
    _scenario("SC06", "河流水质数据分析", "Water Quality Data Analysis", "监测浓度、负荷和站点关系呈现什么特征？", ("water_quality_observations", "station_metadata"), ("streamflow", "river_graph"), ("water_quality",), "reporting_only", ("table", "metrics", "comparison", "report"), "framework_ready", "ready_with_warnings", ("仅为数据分析，不是水质反应模拟。",), recommended=("监测数据 QC", "负荷分析"), not_recommended=("污染物反应预测",)),
    _scenario("SC07", "多站点水质方法实验", "Water Quality Method Experiment", "多站点水质方法在合成数据上表现如何？", ("water_quality_multistation", "river_graph"), ("hydrology_features",), ("water_quality_method_lab",), "water_quality_multistation_experiment", ("timeseries", "metrics", "diagnostic", "report"), "synthetic_demo", "experimental", ("主 water_quality 能力仍为 planned；真实数据 value-added 未测试。",), recommended=("方法研究",), not_recommended=("工程水质预测",)),
    _scenario("SC08", "洪水易发性制图", "Flood Susceptibility Mapping", "哪些位置具有较高的相对洪水易发性？", ("flood_inventory", "conditioning_factors", "spatial_blocks"), ("hydrolite_runoff",), ("flood_susceptibility", "flood_susceptibility_xai"), "flood_susceptibility_mapping", ("map", "metrics", "diagnostic", "report"), "synthetic_demo", "experimental", ("易发性不等于风险；XAI 稳定性不佳；真实验证未测试。",), recommended=("空间方法实验",), not_recommended=("风险损失决策",)),
    _scenario("SC09", "水土流失评估", "Soil Erosion Assessment", "流域土壤侵蚀和泥沙交付的空间差异如何？", ("dem", "land_cover", "soil", "rainfall_erosivity"), ("conservation_practice",), ("rusle", "sediment_delivery"), "erosion_sediment", ("map", "table", "metrics", "report"), "ready_with_warnings", "ready_with_warnings", ("RUSLE 结果不是实测出口输沙量。",), automatic=("gee_catalog",), recommended=("相对侵蚀评估",)),
    _scenario("SC10", "遥感数据检索", "GEE Data Discovery", "哪些官方 Earth Engine 数据适合当前任务？", (), ("bbox", "time_range"), ("gee_catalog_intelligence",), "gee_dataset_discovery", ("table", "comparison", "config", "report"), "framework_ready", "ready_with_warnings", ("目录可离线使用；计算和导出需独立认证。",), automatic=("official_earth_engine_stac",), recommended=("数据发现",)),
    _scenario("SC11", "模型对比与验证", "Model Comparison", "不同模型和情景的结果是否一致、可信？", ("model_outputs",), ("observations",), ("hydrology", "historical_flood_validation"), "hydrology_hec_hms_compare", ("comparison", "metrics", "diagnostic", "report"), "ready_with_warnings", "ready_with_warnings", ("没有独立观测时只能比较模型差异，不能证明准确性。",), recommended=("跨模型审计",)),
    _scenario("SC12", "高级自定义流程", "Custom Workflow", "如何组合已有阶段完成自定义分析？", ("project_workspace",), (), ("method_inspiration_lab",), "full_modeling_workflow", ("config", "artifact", "report"), "framework_ready", "experimental", ("仅适合熟悉 Workflow 和模型边界的高级用户。",), recommended=("高级用户",), advanced=True),
)


def list_scenarios(include_advanced: bool = True) -> list[dict]:
    return [item.as_dict() for item in _SCENARIOS if include_advanced or not item.advanced]


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    for scenario in _SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario_id: {scenario_id}")


def scenario_status_counts() -> dict[str, int]:
    counts = Counter(item.production_status for item in _SCENARIOS)
    return {status: counts.get(status, 0) for status in ("production_ready", "ready_with_warnings", "experimental", "planned", "unavailable")}


def assess_scenario_readiness(scenario_id: str, available_data: Iterable[str] = ()) -> ScenarioReadiness:
    scenario = get_scenario(scenario_id); available = set(available_data)
    required = tuple({"data_id": item, "status": "available" if item in available else "missing"} for item in scenario.required_data)
    optional = tuple({"data_id": item, "status": "available" if item in available else "optional_missing"} for item in scenario.optional_data)
    missing = [item["data_id"] for item in required if item["status"] == "missing"]
    if missing:
        status = "missing_required_data"; action = f"请先准备：{', '.join(missing)}"
    elif scenario.production_status == "experimental":
        status = "ready_for_experiment"; action = "可运行实验，但结果不得直接用于正式决策。"
    else:
        status = "ready_with_warnings" if scenario.limitations else "ready"; action = "检查配置并提交运行。"
    warnings = ("REAL_DATA_VALIDATION_MISSING",) if scenario.validation_level == "synthetic_demo" else ()
    return ScenarioReadiness(scenario_id, status, required, optional, warnings, action)


def validate_scenario_registry() -> dict:
    checks = {item.scenario_id: validate_scenario_definition(item) for item in _SCENARIOS}
    workflow_errors = []
    for item in _SCENARIOS:
        try: get_run_recipe(item.workflow_id)
        except KeyError: workflow_errors.append(item.scenario_id)
    ids = [item.scenario_id for item in _SCENARIOS]
    return {"status": "passed" if all(check["status"] == "passed" for check in checks.values()) and not workflow_errors and len(ids) == len(set(ids)) else "failed", "scenario_count": len(ids), "checks": checks, "workflow_mapping_errors": workflow_errors}


def submit_scenario_run(project_id: str, scenario_id: str) -> dict:
    """Delegate to the existing Run Manager; no second execution system."""
    from hydrolite.run_manager import create_run
    scenario = get_scenario(scenario_id)
    return create_run(project_id, scenario.workflow_id)
