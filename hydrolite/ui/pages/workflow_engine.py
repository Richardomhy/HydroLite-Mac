from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.__version__ import __version__
from hydrolite.ui.components import read_text_if_exists, show_download, show_markdown_file
from hydrolite.ui.state import PROJECT_ROOT, WorkbenchContext
from hydrolite.workflow_engine import (
    create_workflow_plan,
    list_workflow_stages,
    read_workflow_status,
    run_full_workflow,
    run_workflow_stage,
    summarize_workflow_outputs,
)


def _workflow_templates() -> list[Path]:
    root = PROJECT_ROOT / "templates" / "workflows"
    return sorted(root.glob("*.yaml")) if root.exists() else []


def render(context: WorkbenchContext) -> None:
    st.header("全流程工作流")
    st.caption(f"HydroLite Studio v{__version__}")
    st.warning("当前 v0.7.0-dev 是全流程工作流架构阶段，并非所有模型功能已实现。")
    st.info("页面用于生成 dry-run 计划、查看阶段状态和后续路线；不会自动训练 AI、运行长任务或修改 data_raw。")

    project_dir = context.project_dir
    st.write(f"当前项目路径: `{project_dir}`")

    templates = _workflow_templates()
    if not templates:
        st.error("未找到 templates/workflows/ 工作流模板。")
        return
    selected = st.selectbox("工作流模板", templates, format_func=lambda path: path.name)

    stages = list_workflow_stages()
    st.subheader("阶段列表")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "stage_id": stage["stage_id"],
                    "title": stage["title_zh"],
                    "status": stage["status"],
                    "streamlit_page": stage["streamlit_page"],
                    "cli_command": stage["cli_command"],
                }
                for stage in stages
            ]
        ),
        use_container_width=True,
    )

    stage_id = st.selectbox("选择阶段", [stage["stage_id"] for stage in stages])
    stage = next(item for item in stages if item["stage_id"] == stage_id)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader(stage["title_zh"])
        st.write(stage["description_zh"])
        st.write(f"状态: `{stage['status']}`")
        st.write(f"CLI: `{stage['cli_command']}`")
        st.write(f"页面: `{stage['streamlit_page']}`")
    with c2:
        st.write("输入要求")
        st.write(stage["required_inputs"])
        st.write("输出文件")
        st.write(stage["expected_outputs"])
        st.write("安全说明")
        st.write(stage["safety_notes"])

    reports_dir = project_dir / "reports"
    plan_dir = reports_dir / "workflow_plan"
    cols = st.columns(3)
    if cols[0].button("生成 dry-run 计划", use_container_width=True):
        with st.spinner("正在生成工作流计划..."):
            plan = create_workflow_plan(selected, plan_dir)
        st.success(f"计划已生成: `{plan['plan_json']}`")
    if cols[1].button("dry-run 当前阶段", use_container_width=True):
        with st.spinner("正在 dry-run 当前阶段..."):
            result = run_workflow_stage(stage_id, project_dir, config_path=selected, dry_run=True)
        st.json(result)
    if cols[2].button("dry-run 全流程", use_container_width=True):
        with st.spinner("正在 dry-run 全流程..."):
            result = run_full_workflow(project_dir, config_path=selected, dry_run=True)
        st.success(f"工作流报告已生成: `{result['report_path']}`")

    st.subheader("工作流状态")
    st.json(read_workflow_status(project_dir))

    st.subheader("工作流输出")
    st.json(summarize_workflow_outputs(project_dir))
    show_markdown_file("workflow_plan.md", plan_dir / "workflow_plan.md")
    show_markdown_file("workflow_report.md", reports_dir / "workflow_report.md")

    show_download("下载 workflow_plan.json", plan_dir / "workflow_plan.json", "application/json")
    show_download("下载 workflow_status.json", reports_dir / "workflow_status.json", "application/json")
    show_download("下载 workflow_report.md", reports_dir / "workflow_report.md", "text/markdown")

    with st.expander("后续开发路线"):
        st.markdown(read_text_if_exists(PROJECT_ROOT / "docs" / "full_modeling_workflow.md") or "暂无路线文档。")
