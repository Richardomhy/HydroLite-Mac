from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from hydrolite.__version__ import __app_name__, __version__


DEMO_PROJECT = Path("projects/demo_project")
PROGRESS_FILE = Path("reports/demo_progress.json")
SUMMARY_FILE = Path("reports/demo_summary.md")

REQUIRED_STEP_FIELDS = {
    "step_id",
    "title",
    "description",
    "action",
    "expected_output",
    "page_name",
    "cli_equivalent",
    "online_note",
    "local_note",
    "success_files",
}


def _project_path(project_dir: str | Path) -> Path:
    return Path(project_dir).expanduser().resolve()


def get_demo_steps() -> list[dict[str, Any]]:
    return [
        {
            "step_id": "intro",
            "title": "认识 HydroLite Studio",
            "description": "了解项目化工作台、云端演示版和本地完整版的差异。",
            "action": "打开项目首页，阅读版本、在线地址、安全说明和模块概览。",
            "expected_output": "能够说明 HydroLite Studio 覆盖项目、情景、GEE、SWMM、OpenHydroNet 输入和报告导出。",
            "page_name": "项目首页",
            "cli_equivalent": "python -m hydrolite version",
            "online_note": "在线版适合浏览示例输出和演示流程。",
            "local_note": "本地版适合接入 GEE 账号、SWMM 求解器和外部 AI 仓库。",
            "success_files": ["project.yaml"],
        },
        {
            "step_id": "load_project",
            "title": "加载 demo_project",
            "description": "使用内置 demo_project 作为完整演示项目。",
            "action": "在侧栏确认当前项目路径为 projects/demo_project。",
            "expected_output": "项目名称、项目 ID、情景数量和模块启用状态正常显示。",
            "page_name": "项目首页",
            "cli_equivalent": "python -m hydrolite project info projects/demo_project",
            "online_note": "云端默认展示随仓库提供的 demo 项目结构和已有输出。",
            "local_note": "本地可复制项目后替换为自己的数据。",
            "success_files": ["project.yaml", "cases/demo.yaml", "cases/demo_gee.yaml", "cases/demo_swmm.yaml"],
        },
        {
            "step_id": "validate_project",
            "title": "校验项目",
            "description": "检查项目目录、情景 YAML、CSV 输入和 SWMM 配置。",
            "action": "进入数据与校验页面，运行项目校验。",
            "expected_output": "reports/project_validation.xlsx 和 project_validation_report.md 生成。",
            "page_name": "数据与校验",
            "cli_equivalent": "python -m hydrolite project validate projects/demo_project",
            "online_note": "云端可运行轻量校验。",
            "local_note": "本地建议先校验再运行模型。",
            "success_files": ["reports/project_validation.xlsx", "reports/project_validation_report.md"],
        },
        {
            "step_id": "run_demo_gee",
            "title": "运行 demo_gee 情景",
            "description": "运行带观测流量评估的 GEE 示例情景。",
            "action": "进入情景运行页面，选择 demo_gee.yaml 并运行。",
            "expected_output": "demo_gee 生成 result_flow.csv、water_balance.xlsx 和 model_performance.xlsx。",
            "page_name": "情景运行",
            "cli_equivalent": "python -m hydrolite project run projects/demo_project demo_gee.yaml",
            "online_note": "在线版可查看已有结果；实际运行取决于云端写入权限。",
            "local_note": "本地可完整运行并覆盖项目 output/demo_gee。",
            "success_files": [
                "output/demo_gee/result_flow.csv",
                "output/demo_gee/water_balance.xlsx",
                "output/demo_gee/model_performance.xlsx",
            ],
        },
        {
            "step_id": "batch_project",
            "title": "批量运行项目",
            "description": "一次运行 demo、demo_gee 和 demo_swmm 等项目情景。",
            "action": "进入情景运行页面，点击项目批量运行。",
            "expected_output": "output/batch_summary.xlsx 生成，成功/失败状态可追踪。",
            "page_name": "情景运行",
            "cli_equivalent": "python -m hydrolite project batch projects/demo_project",
            "online_note": "云端 SWMM 后端可能降级，但主流程应保持可用。",
            "local_note": "本地隔离 SWMM 求解器可让 demo_swmm 获得完整结果。",
            "success_files": ["output/batch_summary.xlsx"],
        },
        {
            "step_id": "gee_center",
            "title": "查看 GEE 数据中心",
            "description": "查看 GEE 数据计划、摘要、参数建议和 HydroLite 输入产品。",
            "action": "进入 GEE 数据中心页面，查看数据集、状态和输出文件。",
            "expected_output": "能够看到 DEM、CHIRPS、JRC Surface Water 和温度 forcing 相关输出或访问状态。",
            "page_name": "GEE 数据中心",
            "cli_equivalent": "python -m hydrolite gee summarize configs/gee.example.yaml",
            "online_note": "在线版不强制 GEE 登录，只展示已有输出和状态。",
            "local_note": "本地设置 GEE_PROJECT 后可生成真实 GEE 摘要。",
            "success_files": ["../../output/gee/gee_summary.xlsx", "../../output/gee/hydrolite_inputs/gee_chirps_rainfall.csv"],
        },
        {
            "step_id": "swmm_results",
            "title": "查看 SWMM 联动结果",
            "description": "检查 HydroLite 过程线写入 SWMM working.inp 后的管网结果。",
            "action": "进入 SWMM 联动页面，查看 summary、KPI、节点水深、管道流量和 coupling 状态。",
            "expected_output": "demo_swmm 的 swmm_summary.xlsx、swmm_kpis.xlsx 和 coupling_summary.xlsx 可查看。",
            "page_name": "SWMM 联动",
            "cli_equivalent": "python -m hydrolite project run projects/demo_project demo_swmm.yaml",
            "online_note": "云端若 SWMM 后端不可用，页面仍展示已有结果或 failed/skipped 诊断。",
            "local_note": "本地 HYDROLITE_SWMM_PYTHON 可使用隔离求解器。",
            "success_files": [
                "output/demo_swmm/swmm/swmm_summary.xlsx",
                "output/demo_swmm/swmm/swmm_kpis.xlsx",
                "output/demo_swmm/swmm/coupling_summary.xlsx",
            ],
        },
        {
            "step_id": "openhydronet_inputs",
            "title": "查看 OpenHydroNet AI 输入包",
            "description": "了解 HydroLite 如何整理静态属性、气象 forcing、模拟流量和观测流量。",
            "action": "进入 OpenHydroNet AI 输入页面，查看 input package 和质量报告。",
            "expected_output": "看到 static_attributes、meteorological_forcing、hydrolite_streamflow、observed_streamflow 等输入说明。",
            "page_name": "OpenHydroNet AI 输入",
            "cli_equivalent": "python -m hydrolite openhydronet prepare-inputs configs/openhydronet.example.yaml",
            "online_note": "在线版不训练模型，也不要求外部仓库存在。",
            "local_note": "本地可接入外部仓库做环境诊断和后续研究。",
            "success_files": [
                "../../output/openhydronet/inputs/input_manifest.json",
                "../../output/openhydronet/inputs/openhydronet_input_report.md",
            ],
        },
        {
            "step_id": "comparison",
            "title": "查看结果对比",
            "description": "对比多个情景的峰值流量、径流体积、水量平衡、SWMM 和 coupling 指标。",
            "action": "进入结果对比页面，查看表格和图表。",
            "expected_output": "output/comparison/scenario_comparison.xlsx 和对比图表生成。",
            "page_name": "结果对比",
            "cli_equivalent": "python -m hydrolite project compare projects/demo_project",
            "online_note": "在线版适合展示已有对比图。",
            "local_note": "本地可在修改情景后重新对比。",
            "success_files": [
                "output/comparison/scenario_comparison.xlsx",
                "output/comparison/peak_flow_comparison.png",
                "output/comparison/volume_comparison.png",
            ],
        },
        {
            "step_id": "report_export",
            "title": "生成 Word/HTML/Markdown 报告",
            "description": "把项目结果导出为可交付报告和报告包。",
            "action": "进入报告与导出页面，点击一键生成全部。",
            "expected_output": "project_report.md、project_report.docx、project_report.html 和 project_report_bundle.zip 生成。",
            "page_name": "报告与导出",
            "cli_equivalent": "python -m hydrolite report project projects/demo_project",
            "online_note": "在线版若 PDF 后端不可用，会生成 PDF unavailable 说明。",
            "local_note": "本地安装 PDF 后端后可生成 PDF。",
            "success_files": [
                "reports/project_report.md",
                "reports/project_report.docx",
                "reports/project_report.html",
                "reports/project_report_bundle.zip",
            ],
        },
        {
            "step_id": "project_package",
            "title": "导出项目包",
            "description": "把项目配置、案例、对比结果和报告资产打包用于交付。",
            "action": "在报告与导出页面点击导出项目包。",
            "expected_output": "reports/demo_project_package.zip 生成，且不包含 secrets、external 或模型权重。",
            "page_name": "报告与导出",
            "cli_equivalent": "python -m hydrolite project export projects/demo_project",
            "online_note": "云端可下载生成的项目包。",
            "local_note": "本地可将项目包交给同事复现。",
            "success_files": ["reports/demo_project_package.zip"],
        },
        {
            "step_id": "cloud_vs_local",
            "title": "理解在线版与本地版差异",
            "description": "明确 Streamlit Cloud 用于演示，本地环境用于完整专业工作流。",
            "action": "阅读教程页面的路线 A/B/C 和在线/本地差异说明。",
            "expected_output": "能够选择在线快速体验、本地完整演示或工程交付演示路线。",
            "page_name": "教程与 Demo",
            "cli_equivalent": "python -m hydrolite tutorial summary projects/demo_project",
            "online_note": "在线版避免强制认证和重型后端。",
            "local_note": "本地版支持 GEE 认证、SWMM 隔离求解器和 OpenHydroNet 外部仓库诊断。",
            "success_files": ["reports/demo_summary.md"],
        },
    ]


def get_demo_step(step_id: str) -> dict[str, Any]:
    for step in get_demo_steps():
        if step["step_id"] == step_id:
            return step
    raise KeyError(f"Unknown demo step_id: {step_id}")


def get_recommended_demo_project() -> Path:
    return DEMO_PROJECT


def _resolve_success_file(project: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (project / path).resolve()


def get_demo_checklist(project_dir: str | Path) -> list[dict[str, Any]]:
    project = _project_path(project_dir)
    completed = set(read_demo_progress(project).get("completed_steps", []))
    rows: list[dict[str, Any]] = []
    for step in get_demo_steps():
        files = [_resolve_success_file(project, item) for item in step["success_files"]]
        existing = [path for path in files if path.exists()]
        rows.append(
            {
                "step_id": step["step_id"],
                "title": step["title"],
                "page_name": step["page_name"],
                "marked_complete": step["step_id"] in completed,
                "success_file_count": len(existing),
                "expected_file_count": len(files),
                "status": "passed" if len(existing) == len(files) else ("partial" if existing else "missing"),
                "missing_files": [str(path) for path in files if not path.exists()],
                "cli_equivalent": step["cli_equivalent"],
            }
        )
    return rows


def write_demo_progress(project_dir: str | Path, completed_steps: list[str]) -> Path:
    project = _project_path(project_dir)
    reports = project / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    known = {step["step_id"] for step in get_demo_steps()}
    cleaned = [step for step in dict.fromkeys(completed_steps) if step in known]
    path = project / PROGRESS_FILE
    path.write_text(
        json.dumps(
            {
                "app_name": __app_name__,
                "version": __version__,
                "project_dir": str(project),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed_steps": cleaned,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def read_demo_progress(project_dir: str | Path) -> dict[str, Any]:
    path = _project_path(project_dir) / PROGRESS_FILE
    if not path.exists():
        return {"completed_steps": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"completed_steps": []}
    steps = data.get("completed_steps", [])
    data["completed_steps"] = steps if isinstance(steps, list) else []
    return data


def reset_demo_progress(project_dir: str | Path) -> Path:
    return write_demo_progress(project_dir, [])


def generate_demo_summary(project_dir: str | Path) -> Path:
    project = _project_path(project_dir)
    reports = project / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    checklist = get_demo_checklist(project)
    completed = [row for row in checklist if row["marked_complete"]]
    passed = [row for row in checklist if row["status"] == "passed"]
    lines = [
        "# HydroLite Studio Demo Summary",
        "",
        f"- App: `{__app_name__} {__version__}`",
        f"- Project: `{project}`",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Marked complete: `{len(completed)}/{len(checklist)}`",
        f"- Steps with all success files present: `{len(passed)}/{len(checklist)}`",
        "",
        "## Recommended Routes",
        "",
        "- Route A: 在线快速体验，按页面浏览已有结果，不强制认证 GEE/SWMM/OpenHydroNet。",
        "- Route B: 本地完整演示，运行项目校验、批量计算、SWMM 隔离求解器和 GEE 摘要。",
        "- Route C: 工程交付演示，重点展示项目向导、结果对比、报告导出和项目包。",
        "",
        "## Step Checklist",
        "",
        "| Step | Page | Marked | Files | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in checklist:
        lines.append(
            f"| {row['title']} | {row['page_name']} | {row['marked_complete']} | "
            f"{row['success_file_count']}/{row['expected_file_count']} | {row['status']} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Demo progress only records tutorial completion state and does not delete model outputs.",
            "- Cloud deployments can display existing outputs even when optional local backends are unavailable.",
            "- For full GEE/SWMM/OpenHydroNet workflows, use a local environment with the required credentials and solvers.",
        ]
    )
    path = project / SUMMARY_FILE
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
