from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.project_service import list_recent_projects
from hydrolite.run_manager import calculate_run_progress, cancel_run, create_run, inspect_run, retry_failed_run, retry_from_stage, start_run
from hydrolite.run_planner import build_run_plan, estimate_run_plan
from hydrolite.run_recipes import list_run_recipes
from hydrolite.runtime_db import list_run_records
from hydrolite.runtime_mode import detect_runtime_mode
from hydrolite.ui.state import load_app_state, update_app_state


def classify_runs(rows: list[dict]) -> dict[str, list[dict]]:
    return {
        "active": [row for row in rows if row.get("status") in {"queued", "running"}],
        "recent": sorted(rows, key=lambda row: str(row.get("created_at", "")), reverse=True)[:20],
        "failed": [row for row in rows if row.get("status") in {"failed", "timed_out", "blocked"}],
        "warnings": [row for row in rows if row.get("warning_count", 0) or row.get("status") == "completed_with_warnings"],
    }


def _table(rows: list[dict], empty: str) -> None:
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else: st.info(empty)


def render(context) -> None:
    state = load_app_state(st.session_state); st.header("运行中心")
    st.caption(f"运行模式：{detect_runtime_mode()['mode']}。默认先显示状态；Workflow、Tasks、Environment、Logs 和 Artifacts 在 Advanced Mode 展开。")
    try: rows = list_run_records()
    except Exception: rows = []
    groups = classify_runs(rows); tabs = st.tabs(["Active Runs", "Recent Runs", "Failed Runs", "Warnings"])
    for tab, key, empty in zip(tabs, ("active", "recent", "failed", "warnings"), ("没有正在运行的任务。", "尚无运行记录。", "没有失败运行。", "没有运行警告。")):
        with tab: _table(groups[key], empty)
    if state.ui_mode != "advanced":
        st.info("Simple Mode：从场景中心提交运行。切换 Advanced Mode 可查看执行计划和任务控制。")
        return
    st.divider(); st.subheader("Advanced Run Control")
    projects = list_recent_projects()
    if not projects: st.warning("请先在项目页面注册项目。")
    else:
        project_id = st.selectbox("项目", [row["project_id"] for row in projects])
        recipe = st.selectbox("Workflow Recipe", [row["recipe_id"] for row in list_run_recipes()])
        plan = build_run_plan(project_id, recipe); st.json(estimate_run_plan(plan)); st.dataframe(plan["tasks"], use_container_width=True, hide_index=True)
        if st.button("创建 Run"):
            run = create_run(project_id, recipe); update_app_state(st.session_state, selected_run=run["run_id"], last_action="run_created"); st.success(run["run_id"])
    selected = state.selected_run or (rows[-1].get("run_id", "") if rows else "")
    if selected:
        run_id = st.selectbox("Selected Run", [row.get("run_id") for row in rows], index=max(0, [row.get("run_id") for row in rows].index(selected)) if selected in [row.get("run_id") for row in rows] else 0)
        update_app_state(st.session_state, selected_run=run_id)
        controls = st.columns(3)
        if controls[0].button("启动"): st.json(start_run(run_id))
        if controls[1].button("重试失败任务"): st.json(retry_failed_run(run_id))
        if controls[2].button("取消"): st.json(cancel_run(run_id))
        details = inspect_run(run_id); st.progress(int(calculate_run_progress(run_id)["progress"])); st.json(details["run"]); st.dataframe(details["tasks"], use_container_width=True, hide_index=True)
        failed = sorted({row["stage_id"] for row in details["tasks"] if row["status"] in {"failed", "timed_out", "blocked"}})
        if failed:
            stage = st.selectbox("从失败阶段继续", failed)
            if st.button("重试所选阶段"): st.json(retry_from_stage(run_id, stage))
