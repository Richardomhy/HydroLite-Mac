from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.capability_registry import list_capabilities
from hydrolite.project import export_project_package, write_project_summary
from hydrolite.ui.components import recent_files, show_download, show_markdown_file
from hydrolite.ui.state import WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("项目首页")
    try:
        from hydrolite.runtime_db import list_artifact_records, list_project_records, list_run_records
        projects, runs, artifacts = list_project_records(), list_run_records(), list_artifact_records()
        metrics = st.columns(4)
        metrics[0].metric("已注册项目", len(projects))
        metrics[1].metric("Ready 项目", sum(row.get("status") == "ready" for row in projects))
        metrics[2].metric("运行中 Run", sum(row.get("status") in {"queued", "running"} for row in runs))
        metrics[3].metric("失败 Run", sum(row.get("status") == "failed" for row in runs))
        st.caption(f"成果资产：{len(artifacts)}。推荐：项目中心 -> 运行中心 -> 任务中心 -> 成果中心。")
    except Exception as exc:
        st.warning(f"生产运行中心尚未初始化：{exc}")
    st.caption("以项目为中心查看 HydroLite、GEE、SWMM 与 OpenHydroNet 输入工作流。")
    st.info(
        "当前开发版本：HydroLite Studio v0.7.0-dev；稳定 beta：v0.6.0-beta.1。在线版："
        "https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app 。GitHub："
        "https://github.com/Richardomhy/HydroLite-Mac.git 。推荐流程："
        "项目首页 -> 教程与 Demo -> 全流程工作流 -> 数据与校验 -> 情景运行 -> GEE 数据中心 -> SWMM 联动 -> "
        "OpenHydroNet AI 输入 -> 结果对比 -> 报告与导出。"
    )
    st.caption("在线版适合演示和查看示例；本地版适合完整 GEE/SWMM/OpenHydroNet 工作流。")
    st.warning(
        "安全说明：演示不会修改 data_raw 原始数据；不会提交 Google credentials、tokens、API keys、"
        "外部 OpenHydroNet 仓库或模型权重；OpenHydroNet 页面仅生成 input package，不执行真实 AI 预测。"
    )
    st.success("第一次使用？进入左侧导航的 `教程与 Demo` 页面，按步骤完成一次完整软件演示。")
    st.info(
        "Beta 测试反馈：完成演示后可进入左侧 `Beta 反馈` 页面，通过 GitHub Issues 提交 bug、功能建议、"
        "数据模板问题或整体体验反馈。提交前请勿上传敏感数据。"
    )
    st.info("v0.7.0-dev 新增 `全流程工作流` 页面，用于查看阶段状态和 dry-run 计划；planned 阶段不代表已实现。")
    st.info("真实项目建议先进入 `数据中心`：创建工作区、上传并校验数据、生成需求与模型输入，再进入项目向导。原始上传保持只读。")
    st.info("洪水预测 MVP 已进入 `partial`：可运行情景降雨、HydroLite 物理集合、synthetic-demo 水库联算和可选 ML/LSTM smoke test；它不是业务化洪水预警系统。")
    st.subheader("平台能力矩阵")
    st.dataframe(pd.DataFrame(list_capabilities()), use_container_width=True, hide_index=True)
    if not context.project_loaded:
        st.error(context.error_message)
        st.info("请先在终端运行 `python -m hydrolite project create projects/demo_project`，或输入已有项目路径。")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("项目名称", context.project_name)
    c2.metric("项目 ID", context.project_id)
    c3.metric("情景数量", len(context.cases))
    st.write(f"当前项目路径: `{context.project_dir}`")

    st.subheader("project.yaml 概览")
    st.json({k: v for k, v in context.project.items() if k != "_project_dir"})

    modules = context.project.get("modules") or {}
    if isinstance(modules, dict):
        st.subheader("模块启用状态")
        st.dataframe(pd.DataFrame([{"module": k, "enabled": v} for k, v in modules.items()]), use_container_width=True)

    st.subheader("最近输出文件")
    files = recent_files(context.project_dir / "output", limit=20)
    if files:
        st.dataframe(
            pd.DataFrame(
                [{"file": str(path.relative_to(context.project_dir)), "size_bytes": path.stat().st_size} for path in files]
            ),
            use_container_width=True,
        )
    else:
        st.info("暂无项目输出。")

    cols = st.columns(3)
    if cols[0].button("加载项目", use_container_width=True):
        st.success("项目已加载。")
    if cols[1].button("刷新项目状态", use_container_width=True):
        st.rerun()
    if cols[2].button("生成项目摘要", use_container_width=True):
        with st.spinner("正在生成项目摘要..."):
            summary = write_project_summary(context.project_dir)
        st.success(f"项目摘要已生成: `{summary}`")

    show_markdown_file("project_summary.md", context.project_dir / "project_summary.md")
    package = context.project_dir / "reports" / f"{context.project_id}_package.zip"
    show_download("下载当前项目包", package, "application/zip")
