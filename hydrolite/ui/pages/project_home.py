from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.__version__ import __version__
from hydrolite.scenario_registry import list_scenarios
from hydrolite.ui.components.metric_card import render_metric_card
from hydrolite.ui.components.status_badge import status_text
from hydrolite.ui.state import load_app_state, update_app_state


def _recent_runtime() -> tuple[list[dict], list[dict]]:
    try:
        from hydrolite.runtime_db import list_project_records, list_run_records
        return list_project_records(), list_run_records()
    except Exception:
        return [], []


def render(context) -> None:
    state = load_app_state(st.session_state)
    st.title("HydroLite Studio")
    st.subheader("水文 · 水环境 · 洪水风险分析与决策平台")
    st.caption(f"v{__version__} · 当前模式：{'Simple' if state.ui_mode == 'simple' else 'Advanced'}")
    projects, runs = _recent_runtime(); recent_runs = sorted(runs, key=lambda row: str(row.get("created_at", "")), reverse=True)[:5]
    metrics = st.columns(4)
    values = (
        ("当前项目", context.project_name or "未加载"),
        ("数据状态", "待检查" if not context.project_loaded else "已加载项目"),
        ("最近运行", recent_runs[0].get("status", "暂无") if recent_runs else "暂无"),
        ("系统健康", "需关注" if not context.gee_project_detected else "正常"),
    )
    for column, (label, value) in zip(metrics, values):
        with column: render_metric_card(label, value)

    st.subheader("最近项目")
    if projects:
        st.dataframe(pd.DataFrame(projects[-5:]), use_container_width=True, hide_index=True)
    else: st.info("尚无已注册项目。可进入“项目”创建项目，或打开示例项目。")
    left, right = st.columns(2)
    if left.button("创建项目", use_container_width=True): update_app_state(st.session_state, last_action="open_project_wizard")
    if right.button("打开示例项目", use_container_width=True):
        update_app_state(st.session_state, current_project="projects/demo_project", last_action="open_demo_project")
        st.success("示例项目路径已选定；请在侧栏确认当前项目。")

    st.subheader("请选择你的任务")
    quick_ids = {"SC01", "SC03", "SC04", "SC06", "SC08", "SC10", "SC12"}
    quick = [item for item in list_scenarios(include_advanced=state.ui_mode == "advanced") if item["scenario_id"] in quick_ids]
    columns = st.columns(3)
    for index, scenario in enumerate(quick):
        with columns[index % 3].container(border=True):
            st.write(f"**{scenario['name_zh']}**")
            st.caption(scenario["business_question"])
            st.write(status_text(scenario["production_status"]))
            if st.button("选择", key=f"home_{scenario['scenario_id']}"):
                update_app_state(st.session_state, current_scenario=scenario["scenario_id"], last_action="scenario_selected")
                st.success("已选择。请进入“场景”完成数据检查和配置。")

    left, right = st.columns(2)
    with left:
        st.subheader("数据状态")
        if context.project_loaded:
            st.write(f"情景文件：{len(context.cases)}")
            st.write(f"数据目录登记：{len(context.directories)}")
            st.info("下一步：进入“数据”检查缺失、映射、单位和 CRS。")
        else: st.info("没有项目，因此尚未计算数据就绪度。")
    with right:
        st.subheader("最近运行")
        if recent_runs: st.dataframe(pd.DataFrame(recent_runs), use_container_width=True, hide_index=True)
        else: st.info("尚无运行记录。选择场景并提交后会显示在这里。")

    st.subheader("需要处理")
    if not context.project_loaded: st.warning("User Action Required：加载或创建项目。")
    if not context.gee_project_detected: st.warning("GEE 计算认证不可用；官方离线目录仍可使用。")
    st.caption("首页只读取 Registry、运行摘要和项目元数据，不执行训练、GEE refresh 或大型数据扫描。")
