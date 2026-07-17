from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]

AVAILABLE = "available"
PARTIAL = "partial"
PLANNED = "planned"
NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True)
class WorkflowStage:
    stage_id: str
    title_zh: str
    title_en: str
    description_zh: str
    description_en: str
    status: str
    required_inputs: list[str]
    expected_outputs: list[str]
    cli_command: str
    streamlit_page: str
    safety_notes: list[str]
    dependencies: list[str]
    implementation_notes: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "title_zh": self.title_zh,
            "title_en": self.title_en,
            "description_zh": self.description_zh,
            "description_en": self.description_en,
            "status": self.status,
            "required_inputs": self.required_inputs,
            "expected_outputs": self.expected_outputs,
            "cli_command": self.cli_command,
            "streamlit_page": self.streamlit_page,
            "safety_notes": self.safety_notes,
            "dependencies": self.dependencies,
            "implementation_notes": self.implementation_notes,
        }


_STAGES: tuple[WorkflowStage, ...] = (
    WorkflowStage(
        "data_templates",
        "数据模板",
        "Data templates",
        "准备降雨、子流域、河道、观测流量、SWMM 入流映射和 GEE 边界模板。",
        "Prepare standard rainfall, subbasin, reach, observed-flow, SWMM mapping, and GEE boundary templates.",
        AVAILABLE,
        ["templates/data/"],
        ["validated template files", "template summary"],
        "python -m hydrolite templates validate <dataset_dir>",
        "数据模板",
        ["不写入 data_raw；模板不包含 secrets。"],
        ["pandas", "pyyaml"],
        "已实现模板导出和数据规范校验。",
    ),
    WorkflowStage(
        "qgis_preprocessing",
        "QGIS 预处理",
        "QGIS preprocessing",
        "诊断 qgis_process，并将 QGIS/GeoJSON 图层转换为 HydroLite 标准输入和项目。",
        "Diagnose qgis_process and convert QGIS/GeoJSON layers into HydroLite inputs and projects.",
        PARTIAL,
        ["GeoJSON subbasins", "GeoJSON reaches", "GeoJSON basin boundary"],
        ["subbasins.csv", "reaches.csv", "basin_boundary.geojson", "project.yaml"],
        "python -m hydrolite qgis project-workflow <qgis_output_dir> <project_dir>",
        "QGIS Bridge",
        ["当前是文件级 Bridge MVP，不是完整 QGIS 插件。"],
        ["qgis_process optional", "geopandas optional"],
        "已实现诊断、GeoJSON 转换和一键建项目；结果回写 QGIS 后续实现。",
    ),
    WorkflowStage(
        "watershed_delineation",
        "流域划分",
        "Watershed delineation",
        "规划 DEM 填洼、流向、汇流累积、河网提取和子流域划分。",
        "Plan DEM fill, flow direction, accumulation, stream extraction, and subbasin delineation.",
        PLANNED,
        ["DEM", "outlet point", "basin boundary"],
        ["stream network", "subbasins", "delineation report"],
        "not implemented",
        "全流程工作流",
        ["本步骤不执行实际流域划分。"],
        ["QGIS/GRASS/WhiteboxTools/TauDEM planned"],
        "v0.7.x 先做可行性诊断和小样例，避免长任务。",
    ),
    WorkflowStage(
        "gee_inputs",
        "GEE 输入",
        "GEE inputs",
        "从 Google Earth Engine 获取 DEM、CHIRPS、JRC 等摘要和 HydroLite 输入建议。",
        "Create GEE summaries and HydroLite-ready input suggestions from DEM, CHIRPS, and JRC datasets.",
        PARTIAL,
        ["configs/gee.example.yaml", "GEE_PROJECT", "Earth Engine credentials"],
        ["gee_summary.xlsx", "gee_parameter_suggestions.xlsx", "gee_chirps_rainfall.csv"],
        "python -m hydrolite gee summarize configs/gee.example.yaml",
        "GEE 数据中心",
        ["不提交 credentials；云端/未认证环境允许降级。"],
        ["earthengine-api optional"],
        "已实现诊断、摘要和输入产品；真实下载取决于账号权限。",
    ),
    WorkflowStage(
        "hydrolite_simulation",
        "HydroLite 水文模拟",
        "HydroLite simulation",
        "执行 SCS-CN、简化单位线和 Muskingum 河道汇流。",
        "Run SCS-CN runoff, simplified unit hydrograph routing, and Muskingum channel routing.",
        AVAILABLE,
        ["case YAML", "rainfall_csv", "subbasin_csv", "reach_csv"],
        ["result_flow.csv", "summary.xlsx", "water_balance.xlsx", "hydrograph.png"],
        "python -m hydrolite run <case_yaml>",
        "情景运行",
        ["默认先 validate；不修改 data_raw。"],
        ["pandas", "numpy", "matplotlib", "openpyxl"],
        "核心轻量模型已实现，适合快速评估和演示。",
    ),
    WorkflowStage(
        "hec_hms_project",
        "HEC-HMS 项目生成",
        "HEC-HMS project generation",
        "规划将 HydroLite/QGIS/GEE 输入映射为 HEC-HMS 项目文件。",
        "Plan mapping HydroLite/QGIS/GEE inputs into HEC-HMS project files.",
        PLANNED,
        ["basin geometry", "meteorology", "control specs"],
        ["HEC-HMS project folder"],
        "not implemented",
        "全流程工作流",
        ["不做 GUI 自动化；优先命令行/项目文件桥接。"],
        ["HEC-HMS optional"],
        "本阶段仅规划，不生成真实 HEC-HMS 工程。",
    ),
    WorkflowStage(
        "hec_hms_run",
        "HEC-HMS 运行与结果读取",
        "HEC-HMS run and results",
        "规划通过命令行运行 HEC-HMS 并读取 DSS/结果摘要。",
        "Plan command-line HEC-HMS execution and DSS/result summary reading.",
        PLANNED,
        ["HEC-HMS project folder", "HEC-HMS runtime"],
        ["HEC-HMS hydrographs", "DSS summaries"],
        "not implemented",
        "全流程工作流",
        ["本步骤不调用 HEC-HMS，不读取大型 DSS。"],
        ["HEC-HMS optional", "DSS readers planned"],
        "DSS 读取和 macOS 运行能力需要后续诊断。",
    ),
    WorkflowStage(
        "swmm_coupling",
        "SWMM 联动",
        "SWMM coupling",
        "把 HydroLite 出流写入 SWMM working.inp 入流边界并运行可用后端。",
        "Inject HydroLite hydrographs into SWMM working.inp and run available backend.",
        PARTIAL,
        ["swmm.inp_file", "result_flow.csv", "coupling config"],
        ["swmm_summary.xlsx", "coupling_summary.xlsx", "SWMM time series"],
        "python -m hydrolite run cases/demo_swmm.yaml",
        "SWMM 联动",
        ["只修改 working.inp；不修改 data_raw/swmm/demo.inp。"],
        ["pyswmm/swmm-toolkit optional", "external solver optional"],
        "已实现优雅降级和结果提取；后端成功取决于本机环境。",
    ),
    WorkflowStage(
        "flood_forecast",
        "洪水预测",
        "Flood forecast",
        "规划基于降雨预报、情景雨型和阈值的轻量洪水预警。",
        "Plan lightweight flood warning based on forecast rainfall, scenario storms, and thresholds.",
        PLANNED,
        ["forecast rainfall", "thresholds", "simulation outputs"],
        ["flood warning table", "forecast report"],
        "not implemented",
        "全流程工作流",
        ["不训练 AI，不做大规模推理。"],
        ["HydroLite outputs", "optional forecast data"],
        "第一阶段先做规则型预测，不做深度学习。",
    ),
    WorkflowStage(
        "drought_forecast",
        "干旱预测",
        "Drought forecast",
        "规划 SPI/SPEI、降雨距平、径流距平和 GEE 指标的轻量干旱评估。",
        "Plan lightweight drought assessment with SPI/SPEI, rainfall anomaly, runoff anomaly, and GEE indicators.",
        PLANNED,
        ["rainfall history", "temperature optional", "runoff history"],
        ["drought index table", "drought report"],
        "not implemented",
        "全流程工作流",
        ["不做复杂气候模型。"],
        ["pandas", "GEE optional"],
        "先做指标框架和报告骨架。",
    ),
    WorkflowStage(
        "calibration",
        "参数率定与敏感性",
        "Calibration and sensitivity",
        "规划 CN、lag_time、Muskingum K/X 的轻量参数扫描和评估指标。",
        "Plan lightweight parameter scans for CN, lag_time, and Muskingum K/X with performance metrics.",
        PLANNED,
        ["observed_streamflow_csv", "case YAML", "parameter ranges"],
        ["calibration_metrics.xlsx", "sensitivity plots", "calibration report"],
        "not implemented",
        "全流程工作流",
        ["不做复杂优化，不训练模型。"],
        ["observed evaluation outputs"],
        "基于已有观测流量评估扩展。",
    ),
    WorkflowStage(
        "comparison",
        "结果对比",
        "Scenario comparison",
        "对比多个情景的水文、水量平衡、SWMM 和 coupling 指标。",
        "Compare hydrology, water balance, SWMM, and coupling metrics across scenarios.",
        AVAILABLE,
        ["output folders"],
        ["scenario_comparison.xlsx", "comparison plots", "hydrolite_report.md"],
        "python -m hydrolite compare output/",
        "结果对比",
        ["缺失文件优雅跳过。"],
        ["pandas", "matplotlib"],
        "已实现情景对比和自动摘要。",
    ),
    WorkflowStage(
        "report_export",
        "报告导出",
        "Report export",
        "生成 Markdown、Word、HTML、PDF/fallback 和报告包。",
        "Export Markdown, Word, HTML, PDF/fallback, and report bundle.",
        AVAILABLE,
        ["project outputs", "comparison outputs"],
        ["project_report.md", "project_report.docx", "project_report.html", "project_report_bundle.zip"],
        "python -m hydrolite report project <project_dir>",
        "报告与导出",
        ["导出包排除 secrets、external、权重和 data_raw。"],
        ["python-docx optional", "PDF backend optional"],
        "已实现一键项目报告导出。",
    ),
    WorkflowStage(
        "user_manual_export",
        "用户手册导出",
        "User manual export",
        "规划中英文用户手册、FAQ 和故障排查材料的统一导出。",
        "Plan unified export of Chinese/English user manuals, FAQ, and troubleshooting material.",
        PLANNED,
        ["docs/", "README.md"],
        ["user_manual_zh", "user_manual_en"],
        "not implemented",
        "全流程工作流",
        ["本阶段只规划，不生成完整中英文手册包。"],
        ["docs", "report export planned"],
        "已有中文文档，后续整理成可交付手册。",
    ),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def list_workflow_stages() -> list[dict[str, Any]]:
    return [stage.as_dict() for stage in _STAGES]


def get_workflow_stage(stage_id: str) -> dict[str, Any]:
    for stage in _STAGES:
        if stage.stage_id == stage_id:
            return stage.as_dict()
    raise KeyError(f"Unknown workflow stage: {stage_id}")


def _load_workflow_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Workflow config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Workflow config must be a mapping: {path}")
    return data


def validate_workflow_config(config_path: str | Path) -> dict[str, Any]:
    data = _load_workflow_config(config_path)
    known = {stage["stage_id"] for stage in list_workflow_stages()}
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    stages = data.get("stages") or []
    if not isinstance(stages, list) or not stages:
        errors.append("Workflow config must define a non-empty stages list.")
    for item in stages if isinstance(stages, list) else []:
        stage_id = item.get("stage_id") if isinstance(item, dict) else None
        if stage_id not in known:
            errors.append(f"Unknown stage_id: {stage_id}")
            rows.append({"stage_id": stage_id, "status": "failed", "message": "unknown stage"})
            continue
        rows.append(
            {
                "stage_id": stage_id,
                "enabled": bool(item.get("enabled", True)),
                "config_status": item.get("status", "unspecified"),
                "engine_status": get_workflow_stage(stage_id)["status"],
                "message": "ok",
            }
        )
    return {
        "config_path": str(Path(config_path).resolve()),
        "workflow_name": data.get("workflow_name", ""),
        "status": "failed" if errors else "passed",
        "errors": errors,
        "checks": rows,
    }


def create_workflow_plan(config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = _load_workflow_config(config_path)
    validation = validate_workflow_config(config_path)
    configured = data.get("stages") or []
    stage_map = {stage["stage_id"]: stage for stage in list_workflow_stages()}
    plan_stages: list[dict[str, Any]] = []
    for item in configured:
        stage_id = item.get("stage_id") if isinstance(item, dict) else ""
        if stage_id not in stage_map:
            continue
        stage = dict(stage_map[stage_id])
        stage["enabled"] = bool(item.get("enabled", True))
        stage["config_status"] = item.get("status", stage["status"])
        stage["notes"] = item.get("notes", "")
        stage["dry_run_action"] = _dry_run_message(stage)
        plan_stages.append(stage)
    plan = {
        "workflow_name": data.get("workflow_name", Path(config_path).stem),
        "config_path": str(Path(config_path).resolve()),
        "output_dir": str(output),
        "created_at": _utc_now(),
        "dry_run_default": True,
        "validation": validation,
        "stages": plan_stages,
    }
    plan_json = output / "workflow_plan.json"
    plan_md = output / "workflow_plan.md"
    plan_json.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    plan_md.write_text(_render_plan_markdown(plan), encoding="utf-8")
    plan["plan_json"] = str(plan_json)
    plan["plan_md"] = str(plan_md)
    return plan


def _dry_run_message(stage: dict[str, Any]) -> str:
    if stage["status"] == AVAILABLE:
        return f"Would run available command: {stage['cli_command']}"
    if stage["status"] == PARTIAL:
        return f"Would prepare partial stage and avoid unsupported work: {stage['cli_command']}"
    return f"Planned only; not implemented. No model execution will be attempted for {stage['stage_id']}."


def run_workflow_stage(stage_id: str, project_dir: str | Path, config_path: str | Path | None = None, dry_run: bool = True) -> dict[str, Any]:
    stage = get_workflow_stage(stage_id)
    project = Path(project_dir).resolve()
    result = {
        "stage_id": stage_id,
        "project_dir": str(project),
        "config_path": str(Path(config_path).resolve()) if config_path else "",
        "dry_run": dry_run,
        "stage_status": stage["status"],
        "run_status": "dry_run" if dry_run else "not_implemented",
        "message": _dry_run_message(stage) if dry_run else "",
        "created_at": _utc_now(),
    }
    if not dry_run:
        if stage["status"] != AVAILABLE:
            result["message"] = f"Stage {stage_id} is {stage['status']} and is not implemented for execution yet."
        else:
            result["message"] = (
                f"Stage {stage_id} is available, but workflow_engine does not re-run existing commands directly yet. "
                f"Use: {stage['cli_command']}"
            )
    status = read_workflow_status(project)
    status.setdefault("stage_runs", []).append(result)
    write_workflow_status(project, status)
    return result


def run_full_workflow(project_dir: str | Path, config_path: str | Path | None = None, dry_run: bool = True) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    config = Path(config_path) if config_path else PROJECT_ROOT / "templates" / "workflows" / "full_modeling_workflow.yaml"
    plan_dir = project / "reports" / "workflow_plan"
    plan = create_workflow_plan(config, plan_dir)
    runs = [
        run_workflow_stage(stage["stage_id"], project, config_path=config, dry_run=dry_run)
        for stage in plan["stages"]
        if stage.get("enabled", True)
    ]
    report = {
        "project_dir": str(project),
        "config_path": str(config.resolve()),
        "dry_run": dry_run,
        "run_status": "dry_run" if dry_run else "planned_only",
        "stage_count": len(runs),
        "runs": runs,
        "plan_json": plan["plan_json"],
        "created_at": _utc_now(),
    }
    report_path = write_workflow_report(project, report)
    status = read_workflow_status(project)
    status["last_full_workflow"] = report
    status["last_report"] = str(report_path)
    write_workflow_status(project, status)
    report["report_path"] = str(report_path)
    return report


def _workflow_reports_dir(project_dir: str | Path) -> Path:
    path = Path(project_dir).resolve() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_workflow_status(project_dir: str | Path, status: dict[str, Any]) -> Path:
    reports = _workflow_reports_dir(project_dir)
    status = dict(status)
    status["updated_at"] = _utc_now()
    path = reports / "workflow_status.json"
    path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_workflow_status(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).resolve() / "reports" / "workflow_status.json"
    if not path.exists():
        return {"project_dir": str(Path(project_dir).resolve()), "stage_runs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"project_dir": str(Path(project_dir).resolve()), "stage_runs": [], "error": str(exc)}


def write_workflow_report(project_dir: str | Path, report: dict[str, Any]) -> Path:
    reports = _workflow_reports_dir(project_dir)
    path = reports / "workflow_report.md"
    lines = [
        "# HydroLite Full Modeling Workflow Report",
        "",
        f"Project: `{Path(project_dir).resolve()}`",
        f"Created at: `{report.get('created_at', _utc_now())}`",
        f"Dry run: `{report.get('dry_run', True)}`",
        f"Run status: `{report.get('run_status', '')}`",
        "",
        "## Stage Runs",
        "",
    ]
    for run in report.get("runs", []):
        lines.extend(
            [
                f"### {run.get('stage_id')}",
                "",
                f"- stage_status: `{run.get('stage_status')}`",
                f"- run_status: `{run.get('run_status')}`",
                f"- message: {run.get('message', '')}",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def summarize_workflow_outputs(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    reports = project / "reports"
    paths = {
        "workflow_status": reports / "workflow_status.json",
        "workflow_report": reports / "workflow_report.md",
        "workflow_plan": reports / "workflow_plan" / "workflow_plan.json",
    }
    return {name: {"path": str(path), "exists": path.exists()} for name, path in paths.items()}


def _render_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# {plan['workflow_name']}",
        "",
        f"Config: `{plan['config_path']}`",
        f"Created at: `{plan['created_at']}`",
        "",
        "Current v0.7.0-dev is a workflow architecture stage. Planned stages are not executable model features.",
        "",
        "## Stages",
        "",
    ]
    for stage in plan["stages"]:
        lines.extend(
            [
                f"### {stage['stage_id']} - {stage['title_zh']}",
                "",
                f"- Status: `{stage['status']}`",
                f"- Enabled: `{stage['enabled']}`",
                f"- CLI: `{stage['cli_command']}`",
                f"- Streamlit page: `{stage['streamlit_page']}`",
                f"- Dry-run action: {stage['dry_run_action']}",
                "",
                stage["description_zh"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
