from __future__ import annotations

import streamlit as st

from hydrolite.project_service import archive_project, create_project_snapshot, delete_project_registration, import_existing_project, list_recent_projects, register_workspace_as_project, unarchive_project, update_project_readiness
from hydrolite.runtime_paths import get_project_runtime_dir


def render(context) -> None:
    st.header("项目中心")
    st.caption("注册和归档只影响运行中心记录，不删除原始工作区。")
    try:
        import json
        from hydrolite.hindcast import DEFAULT_OUTPUT

        readiness_path = DEFAULT_OUTPUT / "readiness" / "hindcast_readiness.json"
        readiness = json.loads(readiness_path.read_text(encoding="utf-8")) if readiness_path.exists() else {}
        metrics = st.columns(3)
        metrics[0].metric("历史事件数", readiness.get("event_count", 0))
        metrics[1].metric("验证等级", readiness.get("validation_level", "missing_data"))
        metrics[2].metric("同化状态", "available" if (DEFAULT_OUTPUT / "assimilation/assimilation_metrics.xlsx").exists() else "not_run")
    except Exception:
        pass
    try:
        import json
        from hydrolite.drought_workflow import DEFAULT_ROOT as DROUGHT_OUTPUT
        manifest = json.loads((DROUGHT_OUTPUT / "continuous/continuous_model_manifest.json").read_text(encoding="utf-8")) if (DROUGHT_OUTPUT / "continuous/continuous_model_manifest.json").exists() else {}
        drought = json.loads((DROUGHT_OUTPUT / "monitoring/current_drought_status.json").read_text(encoding="utf-8")) if (DROUGHT_OUTPUT / "monitoring/current_drought_status.json").exists() else {}
        metrics = st.columns(4)
        metrics[0].metric("连续数据年数", round(manifest.get("record_days", 0) / 365.25, 1))
        metrics[1].metric("连续模型", manifest.get("water_balance", {}).get("status", "not_run"))
        metrics[2].metric("当前干旱", drought.get("class", "not_run"))
        metrics[3].metric("最近干旱 Run", drought.get("analysis_date", "-"))
    except Exception:
        pass
    path = st.text_input("工作区或项目路径", value=str(context.project_dir))
    left, right = st.columns(2)
    if left.button("注册工作区"):
        try: st.success(register_workspace_as_project(path))
        except Exception as exc: st.error(str(exc))
    if right.button("导入现有项目"):
        try: st.success(import_existing_project(path))
        except Exception as exc: st.error(str(exc))
    projects = list_recent_projects()
    st.dataframe(projects, use_container_width=True)
    if projects:
        project_id = st.selectbox("项目", [row["project_id"] for row in projects])
        a, b, c = st.columns(3)
        if a.button("更新就绪度"): st.json(update_project_readiness(project_id))
        if b.button("创建快照"): st.success(create_project_snapshot(project_id, get_project_runtime_dir(project_id) / "snapshots"))
        archived = next(row["archived"] for row in projects if row["project_id"] == project_id)
        if c.button("恢复归档" if archived else "归档"): st.json(unarchive_project(project_id) if archived else archive_project(project_id))
        confirm = st.checkbox("确认仅删除项目注册（不会删除工作区）")
        if st.button("删除项目注册", disabled=not confirm):
            st.json(delete_project_registration(project_id, confirm=True))
