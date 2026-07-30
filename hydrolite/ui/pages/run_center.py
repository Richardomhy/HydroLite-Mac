from __future__ import annotations

import streamlit as st

from hydrolite.project_service import list_recent_projects
from hydrolite.run_manager import calculate_run_progress, cancel_run, create_run, inspect_run, retry_failed_run, retry_from_stage, start_run
from hydrolite.run_planner import build_run_plan, estimate_run_plan
from hydrolite.run_recipes import list_run_recipes
from hydrolite.runtime_mode import detect_runtime_mode


def render(context) -> None:
    st.header("运行中心")
    st.info(f"运行模式：{detect_runtime_mode()['mode']}；本地重型能力按环境门禁执行。")
    projects = list_recent_projects()
    if not projects:
        st.warning("请先在项目中心注册项目。"); return
    project_id = st.selectbox("项目", [row["project_id"] for row in projects])
    workflow = st.selectbox("运行方案", [row["recipe_id"] for row in list_run_recipes()])
    if st.button("生成运行计划"): st.session_state["runtime_plan"] = build_run_plan(project_id, workflow)
    plan = st.session_state.get("runtime_plan")
    if plan:
        st.json(estimate_run_plan(plan)); st.dataframe(plan["tasks"], use_container_width=True)
        if st.button("创建 Run", disabled=st.session_state.get("run_creating", False)):
            st.session_state["run_creating"] = True
            try:
                run = create_run(project_id, workflow)
                st.session_state["active_run_id"] = run["run_id"]; st.success(run["run_id"])
            finally: st.session_state["run_creating"] = False
    run_id = st.session_state.get("active_run_id")
    if run_id:
        a, b, c = st.columns(3)
        if a.button("启动运行"): st.json(start_run(run_id))
        if b.button("重试失败任务"): st.json(retry_failed_run(run_id))
        if c.button("取消运行"): st.json(cancel_run(run_id))
        details = inspect_run(run_id)
        st.progress(int(calculate_run_progress(run_id)["progress"]))
        st.json(details["run"]); st.dataframe(details["tasks"], use_container_width=True)
        failed_stages = sorted({row["stage_id"] for row in details["tasks"] if row["status"] in {"failed", "timed_out", "blocked"}})
        if failed_stages:
            stage_id = st.selectbox("从失败阶段继续", failed_stages)
            if st.button("重试所选阶段"): st.json(retry_from_stage(run_id, stage_id))
