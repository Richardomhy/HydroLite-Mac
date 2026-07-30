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
        "application_runtime", "应用运行时", "Application runtime",
        "初始化 SQLite 运行库、运行目录、模式和环境诊断。", "Initialize the SQLite runtime, directories, mode, and environment diagnosis.",
        PARTIAL, ["writable runtime directory"], ["runtime database", "environment snapshot"],
        "python -m hydrolite runtime init", "系统与环境",
        ["数据库和日志不进入仓库；不保存凭证。"], ["filesystem", "sqlite3"], "本地、云端和只读模式门禁已实现。",
    ),
    WorkflowStage(
        "project_operations", "项目运维", "Project operations",
        "注册多个工作区并记录就绪度、快照和生命周期。", "Register workspaces and track readiness, snapshots, and lifecycle.",
        PARTIAL, ["application_runtime", "workspace"], ["project record", "project snapshot"],
        "python -m hydrolite projects list", "项目中心",
        ["归档只修改注册记录，不删除用户工作区。"], ["application_runtime"], "项目注册、归档和元数据快照 MVP。",
    ),
    WorkflowStage(
        "workspace", "真实项目工作区", "Real project workspace",
        "创建 raw 只读、standardized/derived 分离且带 manifest 的项目工作区。",
        "Create a project workspace with immutable raw files, separated standardized/derived data, and a manifest.",
        AVAILABLE, ["project name"], ["project.yaml", "workspace_manifest.json"],
        "python -m hydrolite data create-workspace <name> <workspace_dir>", "数据中心",
        ["raw 文件不覆盖；用户上传文件不进入 Git。"], ["filesystem"], "轻量工作区结构已实现。",
    ),
    WorkflowStage(
        "data_center", "数据中心", "Data center",
        "上传、识别、预览并登记真实项目数据。", "Upload, inspect, preview, and register real project data.",
        PARTIAL, ["workspace"], ["data_type_registry.xlsx", "data_quality_summary.xlsx"],
        "python -m hydrolite data quality <workspace_dir>", "数据中心",
        ["原始上传只读；不把未校验数据投入模型。"], ["workspace"], "CSV/XLSX/GeoJSON/ZIP/ASCII 轻量路径可用；重型格式按可选依赖降级。",
    ),
    WorkflowStage(
        "data_acquisition", "外部数据获取", "Data acquisition",
        "生成 GEE、Earthdata、CDS、STAC 获取计划，默认不下载。",
        "Plan GEE, Earthdata, CDS, and STAC acquisition without downloading by default.",
        PARTIAL, ["data_center", "optional connectors"], ["acquisition_plan.xlsx", "acquisition_plan.json"],
        "python -m hydrolite connectors plan <workspace_dir> <workflow_id>", "数据中心",
        ["真实下载必须显式确认；凭证不进入仓库。"], ["data_center", "optional connectors"], "连接器状态和 bounded dry-run 计划已实现。",
    ),
    WorkflowStage(
        "data_standardization", "数据标准化", "Data standardization",
        "执行字段映射、单位与时空质量检查，并写入 standardized。",
        "Apply field mapping, units, temporal/spatial checks, and write standardized copies.",
        PARTIAL, ["data_center", "field mapping", "unit system"], ["standardized data", "lineage manifest"],
        "python -m hydrolite data quality <workspace_dir>", "数据中心",
        ["低置信度映射需人工确认；不修改 raw。"], ["data_center"], "高置信度轻量表格和 GeoJSON 标准化已实现。",
    ),
    WorkflowStage(
        "model_input_build", "模型输入构建", "Model input build",
        "仅从 standardized/derived 构建 HydroLite 及其他模型输入。",
        "Build HydroLite and other model inputs only from standardized/derived data.",
        PARTIAL, ["standardized data", "model requirements"], ["input_build_summary.xlsx", "model input folders"],
        "python -m hydrolite data build-inputs <workspace_dir>", "数据中心",
        ["缺失数据保持 missing；不从 raw 直接运行模型。"], ["data_standardization"], "HydroLite 输入可生成；其他模型按数据就绪度准备。",
    ),
    WorkflowStage(
        "run_orchestration", "运行编排", "Run orchestration",
        "将工作流转换为可追踪、可取消、可重试的本地任务。", "Convert workflows into traceable, cancellable, retryable local tasks.",
        PARTIAL, ["project_operations", "model_input_build"], ["run plan", "task records", "run report"],
        "python -m hydrolite runs plan <project_id> <workflow_id>", "运行中心",
        ["外部进程使用参数数组和独立进程组；默认单并发。"], ["application_runtime", "project_operations"], "SQLite 队列和失败隔离 MVP。",
    ),
    WorkflowStage(
        "artifact_management", "成果资产管理", "Artifact management",
        "登记、校验、预览和安全打包每次 Run 的成果。", "Register, validate, preview, and safely bundle run artifacts.",
        PARTIAL, ["run_orchestration"], ["artifact index", "artifact validation", "artifact bundle"],
        "python -m hydrolite artifacts list", "成果中心",
        ["大型 DSS/HDF5/NetCDF 仅展示元数据；bundle 排除敏感内容。"], ["run_orchestration"], "轻量成果索引和质量验证 MVP。",
    ),
    WorkflowStage(
        "deployment_readiness", "部署就绪度", "Deployment readiness",
        "诊断本地启动、Streamlit Cloud 降级、权限和入口。", "Diagnose local launch, Streamlit Cloud fallback, permissions, and entrypoint.",
        PARTIAL, ["application_runtime"], ["deployment diagnosis"], "python -m hydrolite runtime diagnose", "系统与环境",
        ["云端禁止本地 QGIS、HEC-HMS 和大型下载。"], ["application_runtime"], "本地启动/停止脚本和云端门禁 MVP。",
    ),
    WorkflowStage(
        "desktop_build", "macOS 桌面构建", "macOS desktop build",
        "构建隔离 Python 后端和 SwiftUI/WKWebView 原生壳。", "Build the isolated Python backend and SwiftUI/WKWebView shell.",
        PARTIAL, ["hydrolite-build", "Swift 6"], ["HydroLite Studio.app", "build reports"],
        "python -m hydrolite desktop build", "系统与环境",
        ["仅 arm64；产物不进入 Git。"], ["deployment_readiness"], "PyInstaller onedir 与 SwiftPM MVP。",
    ),
    WorkflowStage(
        "desktop_signing", "macOS 签名", "macOS signing",
        "逐层签名并审计 Bundle。", "Sign nested code and audit the bundle.",
        PARTIAL, ["desktop_build"], ["signing_audit.md", "macho_inventory.xlsx"],
        "python -m hydrolite desktop sign ad_hoc", "系统与环境",
        ["Developer ID 需要外部凭证；不提交证书。"], ["desktop_build"], "本地 ad-hoc 可用，Developer ID 需凭证。",
    ),
    WorkflowStage(
        "desktop_packaging", "macOS 发行包", "macOS packaging",
        "生成并验证 ZIP、DMG 和校验和。", "Create and validate ZIP, DMG, and checksums.",
        PARTIAL, ["desktop_signing"], ["ZIP", "DMG", "SHA256SUMS"],
        "python -m hydrolite desktop package-dmg", "系统与环境",
        ["发行包不包含用户数据、凭证或外部软件。"], ["desktop_signing"], "本地 ad-hoc 发行包 MVP。",
    ),
    WorkflowStage(
        "desktop_notarization", "macOS 公证", "macOS notarization",
        "执行 Developer ID 与 notarytool 门禁，默认 dry-run。", "Run Developer ID and notarytool gates; dry-run by default.",
        PARTIAL, ["developer_id signing", "notary profile"], ["notarization_report.md"],
        "python -m hydrolite desktop notarize dry-run", "系统与环境",
        ["无凭证时状态为 credentials_required；绝不伪造公证。"], ["desktop_signing", "desktop_packaging"], "当前需 Apple Developer 凭证。",
    ),
    WorkflowStage(
        "desktop_update_readiness", "macOS 安全更新", "macOS secure updates",
        "检查 HTTPS feed、签名元数据和手动更新降级。", "Check HTTPS feed, signing metadata, and manual-update fallback.",
        PARTIAL, ["signed update manifest"], ["update_readiness_report.md"],
        "python -m hydrolite desktop update-status", "系统与环境",
        ["无 Feed/EdDSA 私钥时不静默升级。"], ["desktop_packaging"], "当前为手动 manifest fallback，Sparkle feed 未配置。",
    ),
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
        "诊断水文栅格后端，对小型 DEM 执行填洼、汇流累积和河网/分区示例。",
        "Diagnose hydrologic raster backends and run a small DEM fill, accumulation, stream, and basin MVP.",
        PARTIAL,
        ["DEM", "outlet point", "basin boundary"],
        ["watershed_report.md", "basin_boundary.geojson", "stream_network.geojson", "subbasins.geojson"],
        "python -m hydrolite watershed mvp",
        "流域划分",
        ["当前是 MVP；fallback 几何和参数必须经专业 GIS 人工复核。"],
        ["qgis_process optional", "Python standard-library fallback"],
        "已实现后端探测、小型合成 DEM 和明确标记的 fallback 产物；不是专业流域划分工具。",
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
        "hydrologic_balance_audit", "水量平衡审计", "Hydrologic balance audit",
        "审计累计 SCS-CN、完整单位线尾部和河道路由蓄量。", "Audit cumulative SCS-CN, full unit-hydrograph tails, and reach storage.", PARTIAL,
        ["hydrolite_simulation"], ["hydrologic_balance_ledger.xlsx", "water_balance_audit_report.md", "flood_forecast_gate.json"],
        "python -m hydrolite balance audit <project>", "水量平衡审计",
        ["数值诊断不是工程验收；洪水预测仍保持 planned。"], ["hydrolite_simulation"], "完整过程线用于平衡，比较窗口单独输出。",
    ),
    WorkflowStage(
        "hec_hms_project",
        "HEC-HMS 项目生成",
        "HEC-HMS project generation",
        "将 HydroLite/QGIS/Watershed 输入映射为需人工复核的 HEC-HMS 项目骨架。",
        "Map HydroLite/QGIS/Watershed inputs into an unverified HEC-HMS project skeleton for manual review.",
        PARTIAL,
        ["basin geometry", "meteorology", "control specs"],
        ["hec_hms_project_report.md", "hec_hms_mapping_summary.xlsx", "hec_hms_precipitation_mapping.xlsx", "hec_hms_rainfall_gate.xlsx"],
        "python -m hydrolite hms create-project projects/qgis_workflow_project output/hec_hms_project",
        "HEC-HMS",
        ["当前为 project_generation_mvp / unverified；不做 GUI 自动化。"],
        ["HEC-HMS optional", "Java runtime optional for diagnosis"],
        "已验证 HydroLite rainfall.csv 规范化、HEC-DSS 写入/回读、Weighted Gages 映射与 Project.open；阶段仍为 partial。",
    ),
    WorkflowStage(
        "hec_hms_run",
        "HEC-HMS 运行与结果读取",
        "HEC-HMS run and results",
        "探测 HEC-HMS 命令行，支持默认 dry-run、短时 probe、可选 execute 和基础输出摘要。",
        "Probe HEC-HMS command-line support with default dry-run, short probe, optional execution, and basic output summaries.",
        PARTIAL,
        ["HEC-HMS project folder", "HEC-HMS runtime"],
        ["hec_hms_rainfall_compute.md", "hec_hms_result_catalog.xlsx", "hms_timeseries_read_manifest.json", "outlet_selection.json"],
        "python -m hydrolite hms run output/hec_hms_project --dry-run",
        "HEC-HMS",
        ["默认 dry-run；execute 必须显式请求并受 120 秒 timeout 限制；不做 GUI 自动化。"],
        ["HEC-HMS optional", "HEC-HMS bundled HEC-DSS Java classes optional"],
        "HEC-HMS compute verified；DSS result catalog verified；flow extraction and topology-backed outlet comparison verified for the small demo. Calibration and forecast are not completed, so this stage remains partial.",
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
        "icesat2_water_depth", "ICESat-2 水深", "ICESat-2 water depth",
        "受限沿轨水面/浅水约束诊断。", "Constrained along-track surface/depth constraint diagnosis.", PARTIAL,
        ["waterbody boundary", "local HDF5 or bounded Earthdata access"], ["depth_profiles.csv", "stage_area_volume.csv"],
        "python -m hydrolite icesat2 demo", "ICESat-2 水深",
        ["不将沿轨结果称为完整测深。"], ["watershed_delineation"], "本地合成 demo 与可选依赖诊断已实现。",
    ),
    WorkflowStage(
        "rusle_erosion", "RUSLE 土壤侵蚀", "RUSLE erosion",
        "计算年平均片蚀和细沟侵蚀情景。", "Calculate annual average sheet and rill erosion scenarios.", PARTIAL,
        ["projected DEM", "R/K/LS/C/P"], ["soil_loss_baseline.asc", "subbasin_soil_loss.xlsx"],
        "python -m hydrolite rusle demo", "RUSLE 土壤侵蚀",
        ["不等同于入河泥沙或单场侵蚀。"], ["watershed_delineation"], "合成 ASCII 因子 MVP；栅格重投影后续实现。",
    ),
    WorkflowStage(
        "conservation_scenario", "水土保持情景", "Conservation scenario",
        "生成不覆盖原始输入的 HydroLite 保水情景。", "Generate a non-destructive HydroLite water-retention scenario.", PARTIAL,
        ["hydrolite_simulation", "rusle_erosion"], ["conservation_summary.xlsx"],
        "python -m hydrolite conservation run <project> <scenario>", "RUSLE 土壤侵蚀",
        ["单事件保水量不得年化。"], ["hydrolite_simulation", "rusle_erosion"], "通过径流体积差计算保水量。",
    ),
    WorkflowStage(
        "reservoir_routing", "水库调蓄", "Reservoir routing",
        "使用明确库容与泄流曲线进行 level-pool 调蓄。", "Route a reservoir with explicit storage and discharge curves.", PARTIAL,
        ["HydroLite inflow", "stage-storage curve", "discharge curve"], ["reservoir_routing_timeseries.csv", "reservoir_routing_summary.xlsx"],
        "python -m hydrolite reservoir demo", "水库调蓄",
        ["库容曲线不等于泄流曲线；缺泄流曲线时禁止路由。"], ["hydrolite_simulation", "icesat2_water_depth"], "原创合成曲线 level-pool MVP。",
    ),
    WorkflowStage(
        "sediment_delivery", "泥沙交付与拦沙", "Sediment delivery and trapping",
        "以显式 SDR 将 RUSLE 片蚀转换为坡面交付泥沙，并可选拦沙。", "Convert RUSLE sheet/rill erosion to hillslope delivery with explicit SDR and optional trapping.", PARTIAL,
        ["RUSLE", "SDR", "optional reservoir"], ["sediment_delivery_summary.xlsx", "sediment_delivery_ledger.xlsx"],
        "python -m hydrolite sediment demo", "泥沙交付与拦沙",
        ["不把 RUSLE 当作出口输沙；沟蚀、河岸和河床过程保持 missing。"], ["rusle_erosion", "reservoir_routing"], "合成未率定 SDR MVP。",
    ),
    WorkflowStage(
        "watershed_accounting", "流域综合核算", "Watershed accounting",
        "列出水量与泥沙核算项及缺失项。", "List water/soil accounting components and gaps.", PARTIAL,
        ["HydroLite", "HEC-HMS", "ICESat-2", "RUSLE"], ["water_accounting_ledger.xlsx", "soil_sediment_accounting_ledger.xlsx"],
        "python -m hydrolite accounting build <project>", "流域综合核算",
        ["默认 partial；missing 绝不视为零。"], ["hydrolite_simulation", "hec_hms_run", "icesat2_water_depth", "rusle_erosion", "conservation_scenario", "reservoir_routing", "sediment_delivery"], "核算完整性审计 MVP。",
    ),
    WorkflowStage("event_catalog", "洪水事件目录", "Flood event catalog", "识别并审计独立洪水事件。", "Detect and audit independent flood events.", PARTIAL, ["rainfall_observed", "streamflow_observed"], ["flood_event_catalog.xlsx"], "python -m hydrolite hindcast event-catalog <workspace>", "历史洪水验证", ["不覆盖原始观测。"], ["data_standardization"], "真实数据不足时保持降级状态。"),
    WorkflowStage("observation_quality_control", "观测质量控制", "Observation quality control", "检查缺测、重复、峰值、平线和元数据变化。", "Check gaps, duplicates, spikes, flatlines, and metadata changes.", PARTIAL, ["observations"], ["observation_qc_summary.xlsx"], "python -m hydrolite hindcast observation-qc <workspace>", "历史洪水验证", ["修正写入 standardized 并保留审计。"], ["event_catalog"], "轻量表格质量控制。"),
    WorkflowStage("observation_mapping", "观测映射", "Observation mapping", "映射测站与河段或出口。", "Map stations to reaches or outlets.", PARTIAL, ["station metadata", "model structure"], ["station_model_mapping.xlsx"], "python -m hydrolite hindcast map-stations <workspace>", "历史洪水验证", ["低置信度映射需人工确认。"], ["observation_quality_control"], "显式 ID 优先。"),
    WorkflowStage("event_split", "事件划分", "Event split", "按时间划分率定、验证和测试事件。", "Chronologically split calibration, validation, and test events.", PARTIAL, ["event catalog"], ["event_split.yaml"], "python -m hydrolite hindcast split-events <workspace>", "历史洪水验证", ["不随机打乱，不允许事件泄漏。"], ["event_catalog"], "支持留一事件法。"),
    WorkflowStage("multi_event_hindcast", "多事件回放", "Multi-event hindcast", "运行 HydroLite 多事件历史回放。", "Run multi-event HydroLite hindcasts.", PARTIAL, ["event datasets", "model inputs"], ["event_metrics.xlsx"], "python -m hydrolite hindcast run-batch <project>", "历史洪水验证", ["HEC-HMS 失败不阻断 HydroLite。"], ["event_split", "observation_mapping"], "全过程线与事件水量平衡。"),
    WorkflowStage("multi_event_calibration", "多事件率定", "Multi-event calibration", "在率定事件上选择稳健参数。", "Select robust parameters using calibration events only.", PARTIAL, ["calibration events"], ["robust_parameters.yaml"], "python -m hydrolite hindcast calibrate-multi <project>", "历史洪水验证", ["验证和测试事件不参与率定。"], ["multi_event_hindcast"], "候选数有界。"),
    WorkflowStage("data_assimilation", "流量数据同化", "Flow data assimilation", "比较 open-loop、nudging 和轻量 EnKF analysis。", "Compare open-loop, nudging, and lightweight EnKF analysis.", PARTIAL, ["observations", "hindcast"], ["assimilation_metrics.xlsx"], "python -m hydrolite assimilation batch <project>", "历史洪水验证", ["analysis 不得称为纯预测。"], ["multi_event_hindcast"], "EnKF 默认 20、最大 30。"),
    WorkflowStage("lead_time_validation", "提前期验证", "Lead-time validation", "验证 1/3/6/12 小时提前期性能。", "Validate performance at 1/3/6/12-hour leads.", PARTIAL, ["assimilation results"], ["lead_time_metrics.xlsx"], "python -m hydrolite hindcast lead-time <project>", "历史洪水验证", ["短事件跳过不适用提前期。"], ["data_assimilation"], "对比 open-loop、同化和持续性。"),
    WorkflowStage("model_validation", "模型验证", "Model validation", "汇总事件、最差事件、稳定性和适用等级。", "Summarize events, worst cases, stability, and validation level.", PARTIAL, ["hindcast metrics"], ["model_validation_summary.xlsx"], "python -m hydrolite hindcast summarize <output_dir>", "历史洪水验证", ["软件诊断不等于工程验收。"], ["multi_event_hindcast", "lead_time_validation"], "合成数据与真实验证分开。"),
    WorkflowStage(
        "flood_forecast",
        "洪水预测",
        "Flood forecast",
        "运行情景降雨、HydroLite 物理集合、可选本地 HEC-HMS、合成水库与可选 ML/LSTM smoke test。",
        "Run scenario rainfall, HydroLite physical members, optional local HEC-HMS, synthetic reservoir routing, and optional ML/LSTM smoke tests.",
        PARTIAL,
        ["forecast rainfall contract", "hydrologic_balance_audit", "thresholds", "simulation outputs"],
        ["rainfall_member_summary.xlsx", "member_run_summary.xlsx", "ensemble_timeseries.csv", "peak_distribution.xlsx", "reservoir_stage_distribution.xlsx", "flood_forecast_report_zh.md", "flood_forecast_report_en.md", "flood_forecast_bundle.zip"],
        "python -m hydrolite forecast run-demo",
        "洪水预测",
        ["情景成员比例不是严格概率；不生成法定预警；真实 LSTM 数据门禁未通过。"],
        ["hydrologic_balance_audit", "hydrolite_simulation", "optional hec_hms_run", "optional reservoir_routing", "optional machine_learning", "optional deep_learning"],
        "HydroLite physical ensemble verified; HEC-HMS event members optional_local; HEC-HMS Reservoir blocked; ML optional; real-project LSTM framework only; synthetic smoke tests supported; operational forecast not validated.",
    ),
    WorkflowStage("continuous_hydrology", "连续水文", "Continuous hydrology", "执行日尺度连续水量循环并保留跨日状态。", "Run daily continuous water cycling with persistent state.", PARTIAL, ["daily_meteorology"], ["daily_water_balance.csv", "daily_states.csv"], "python -m hydrolite continuous run <config>", "干旱分析与预测", ["逐日水量平衡门禁；不修改原始数据。"], ["pandas", "numpy"], "双层土壤桶、线性地下水和跨日河道储量 MVP。"),
    WorkflowStage("evapotranspiration", "蒸散发", "Evapotranspiration", "选择用户 PET、FAO56、Hargreaves 或合成 Demo 气候态。", "Select user PET, FAO56, Hargreaves, or synthetic demo climatology.", PARTIAL, ["meteorology"], ["pet_method_report.md"], "python -m hydrolite continuous run <config>", "干旱分析与预测", ["缺输入不伪造 Penman-Monteith。"], ["continuous_hydrology"], "PET 方法门禁和实际蒸散水分胁迫 MVP。"),
    WorkflowStage("soil_water_balance", "土壤水", "Soil water balance", "连续更新表层和下层土壤水。", "Continuously update upper and lower soil water.", PARTIAL, ["soil parameters", "PET", "precipitation"], ["daily_states.csv"], "python -m hydrolite continuous run <config>", "干旱分析与预测", ["状态不按年/月重置。"], ["continuous_hydrology"], "入渗、蒸散、渗漏和壤中流 MVP。"),
    WorkflowStage("groundwater_baseflow", "地下水与基流", "Groundwater and baseflow", "以线性水库更新概念地下水和基流。", "Update conceptual groundwater and baseflow with a linear reservoir.", PARTIAL, ["percolation"], ["groundwater_storage_timeseries.png"], "python -m hydrolite continuous run <config>", "干旱分析与预测", ["模型储量不称实测地下水位。"], ["soil_water_balance"], "线性地下水库和深层损失 MVP。"),
    WorkflowStage("drought_indices", "干旱指标", "Drought indices", "计算 SPI、SPEI、SSI、百分位和综合指数。", "Calculate SPI, SPEI, SSI, percentiles, and a composite index.", PARTIAL, ["continuous_hydrology"], ["drought_indices_monthly.csv"], "python -m hydrolite drought indices <project>", "干旱分析与预测", ["短记录和拟合失败明确降级。"], ["continuous_hydrology"], "1/3/6/12/24 月指标和基线期元数据 MVP。"),
    WorkflowStage("drought_event_catalog", "干旱事件目录", "Drought event catalog", "识别持续干旱期、严重度和恢复。", "Detect persistent drought periods, severity, and recovery.", PARTIAL, ["drought_indices"], ["drought_event_catalog.xlsx"], "python -m hydrolite drought events <project>", "干旱分析与预测", ["单个低值不称长期事件。"], ["drought_indices"], "多指标历史事件目录 MVP。"),
    WorkflowStage("drought_monitoring", "干旱监测", "Drought monitoring", "按气象、农业、水文、水库和地下水分类评估当前状态。", "Assess current meteorological, agricultural, hydrological, reservoir, and groundwater status.", PARTIAL, ["drought_indices"], ["current_drought_status.xlsx"], "python -m hydrolite drought monitor <project>", "干旱分析与预测", ["过期数据标记 stale_data；非业务预警。"], ["drought_indices"], "时效、缺源和置信度显式记录。"),
    WorkflowStage("drought_scenarios", "干旱情景", "Drought scenarios", "生成有界合成或用户情景集合。", "Generate bounded synthetic or user scenario ensembles.", PARTIAL, ["daily_meteorology"], ["forcing_members.csv"], "python -m hydrolite drought scenario-demo", "干旱分析与预测", ["用户情景不称气象预报。"], ["continuous_hydrology"], "降雨、温度、PET 和季节偏移情景 MVP。"),
    WorkflowStage(
        "drought_forecast",
        "干旱预测",
        "Drought forecast",
        "以连续状态运行多成员、多提前期干旱情景或外部预报。",
        "Run multi-member and multi-lead drought scenarios or external forecasts from continuous states.",
        PARTIAL,
        ["drought_scenarios", "continuous state"],
        ["drought_forecast_members.csv", "drought_index_quantiles.csv"],
        "python -m hydrolite drought forecast-demo",
        "干旱分析与预测",
        ["情景成员比例不称概率；当前非业务预警系统。"],
        ["drought_scenarios", "continuous_hydrology"],
        "1/3/6/12 月情景集合、失败成员隔离和水量门禁 MVP。",
    ),
    WorkflowStage("drought_data_assimilation", "干旱状态同化", "Drought data assimilation", "用土壤水、地下水或水库观测更新 analysis state。", "Update the analysis state with soil, groundwater, or reservoir observations.", PARTIAL, ["continuous state", "observations"], ["assimilation_adjustments.csv"], "python -m hydrolite drought assimilation <project>", "干旱分析与预测", ["调整量显式进入账本。"], ["continuous_hydrology"], "Nudging 状态更新和 open-loop 对比 MVP。"),
    WorkflowStage("drought_model_validation", "干旱模型验证", "Drought model validation", "检查连续水量门禁、指标和预测成果完整性。", "Validate the continuous balance gate and drought artifacts.", PARTIAL, ["drought outputs"], ["drought_model_manifest.json"], "python -m hydrolite drought validate output/drought_model", "干旱分析与预测", ["水量门禁失败时关闭正式预测。"], ["drought_forecast"], "合成能力与真实数据就绪度分开记录。"),
    WorkflowStage(
        "calibration",
        "参数率定与敏感性",
        "Calibration and sensitivity",
        "执行受控 CN、lag_time、Muskingum K/X 参数扫描，并区分实测率定与 HMS 跨模型对齐。",
        "Run bounded CN, lag_time, and Muskingum K/X scans and distinguish observed calibration from HMS cross-model alignment.",
        PARTIAL,
        ["observed_streamflow_csv", "case YAML", "parameter ranges"],
        ["parameter_sensitivity.xlsx", "calibration_candidates.xlsx", "best_candidate.yaml", "best_alignment_report.md"],
        "python -m hydrolite calibration search <project_dir> <hms_comparison_dir> --max-candidates 30",
        "参数率定与敏感性",
        ["不做复杂优化，不训练模型。"],
        ["observed evaluation outputs"],
        "支持 observed calibration（若存在实测流量）和 HMS alignment；多事件验证与高级优化尚未实现。",
    ),
    WorkflowStage(
        "comparison",
        "结果对比",
        "Scenario comparison",
        "对比多情景结果，并支持已完成事件的 HEC-HMS/HydroLite 出口过程与指标对比。",
        "Compare scenarios and completed-event HEC-HMS/HydroLite outlet hydrographs and metrics.",
        AVAILABLE,
        ["output folders"],
        ["scenario_comparison.xlsx", "aligned_outlet_timeseries.csv", "event_metrics.xlsx", "model_comparison_metrics.xlsx", "comparison_report.md", "hec_hms_comparison_bundle.zip"],
        "python -m hydrolite compare output/",
        "结果对比",
        ["缺失文件优雅跳过。"],
        ["pandas", "matplotlib"],
        "已实现情景对比，以及小型已完成事件的 HEC-HMS/HydroLite 精确时标对齐、水文指标和差异报告；未完成率定或预报。",
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
