from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st

from hydrolite.project_service import archive_project, create_project_snapshot, import_existing_project, list_recent_projects, register_workspace_as_project, unarchive_project, update_project_readiness
from hydrolite.runtime_db import list_artifact_records, list_run_records
from hydrolite.runtime_paths import get_project_runtime_dir
from hydrolite.scenario_registry import get_scenario
from hydrolite.ui.components.artifact_list import render_artifact_list
from hydrolite.ui.components.metric_card import render_metric_card
from hydrolite.ui.state import load_app_state


def project_dashboard_payload(context) -> dict:
    runs = [row for row in list_run_records() if not context.project_id or row.get("project_id") == context.project_id]
    return {
        "project_name": context.project_name or "未加载", "project_status": "loaded" if context.project_loaded else "missing",
        "study_area": context.project.get("study_area", context.project.get("region", "未设置")) if context.project_loaded else "未设置",
        "created_at": context.project.get("created_at", "未记录") if context.project_loaded else "未记录",
        "last_run": runs[-1].get("created_at", "暂无") if runs else "暂无",
        "current_scenario": load_app_state(st.session_state).current_scenario or "未选择",
        "data_completeness": "待校验" if context.project_loaded else "无项目", "model_readiness": "按场景检查",
    }


def render(context) -> None:
    st.header("项目 Dashboard")
    try: payload = project_dashboard_payload(context)
    except Exception: payload = {"project_name": context.project_name or "未加载", "project_status": "unknown", "study_area": "未设置", "created_at": "未记录", "last_run": "暂无", "current_scenario": "未选择", "data_completeness": "待校验", "model_readiness": "按场景检查"}
    columns = st.columns(4)
    for column, key, label in zip(columns, ("project_name", "project_status", "data_completeness", "model_readiness"), ("项目", "状态", "数据完整度", "模型就绪度")):
        with column: render_metric_card(label, payload[key])
    st.caption(f"研究区：{payload['study_area']} · 创建时间：{payload['created_at']} · 最后运行：{payload['last_run']} · 当前场景：{payload['current_scenario']}")
    tabs = st.tabs(["Overview", "Data", "Scenarios", "Runs", "Results", "Reports"])
    with tabs[0]:
        path = st.text_input("工作区或项目路径", value=str(context.project_dir))
        a, b = st.columns(2)
        if a.button("注册工作区"):
            try: st.success(register_workspace_as_project(path))
            except Exception as exc: st.error(str(exc))
        if b.button("导入现有项目"):
            try: st.success(import_existing_project(path))
            except Exception as exc: st.error(str(exc))
        projects = list_recent_projects()
        if projects: st.dataframe(pd.DataFrame(projects), use_container_width=True, hide_index=True)
        else: st.info("暂无已注册项目。项目向导可创建新项目；不会覆盖已有目录。")
        if context.project_loaded:
            actions = st.columns(3)
            if actions[0].button("更新就绪度"): st.json(update_project_readiness(context.project_id))
            if actions[1].button("创建快照"): st.success(create_project_snapshot(context.project_id, get_project_runtime_dir(context.project_id) / "snapshots"))
            if actions[2].button("归档/恢复"):
                project = next((row for row in projects if row.get("project_id") == context.project_id), {})
                st.json(unarchive_project(context.project_id) if project.get("archived") else archive_project(context.project_id))
    with tabs[1]:
        st.json(context.directories if context.project_loaded else {"status": "no_project"})
        if not context.project_loaded: st.info("加载项目后显示数据目录与完整度。")
    with tabs[2]:
        state = load_app_state(st.session_state)
        if state.current_scenario:
            scenario = get_scenario(state.current_scenario); st.json(scenario.as_dict())
        else: st.info("尚未选择场景。请进入场景中心。")
    with tabs[3]:
        rows = [row for row in list_run_records() if row.get("project_id") == context.project_id] if context.project_loaded else []
        if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else: st.info("暂无项目运行。")
    artifacts = [row for row in list_artifact_records() if row.get("project_id") == context.project_id] if context.project_loaded else []
    with tabs[4]: render_artifact_list(artifacts)
    with tabs[5]: render_artifact_list([row for row in artifacts if str(row.get("artifact_type", "")).lower() == "report"])
