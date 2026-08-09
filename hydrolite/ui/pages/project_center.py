from __future__ import annotations

from pathlib import Path
import tempfile
import pandas as pd
import streamlit as st

from hydrolite.deliverable_package import create_delivery_bundle, create_project_package, import_project_package
from hydrolite.delivery_review import (
    acknowledge_warning, approve_delivery, assess_delivery_readiness, create_deliverable,
    list_deliverables, reject_delivery, request_delivery_changes, review_delivery, submit_delivery,
)
from hydrolite.integrity_verification import verify_project_package
from hydrolite.project_service import archive_project, create_project_snapshot, import_existing_project, list_recent_projects, register_workspace_as_project, unarchive_project, update_project_readiness
from hydrolite.project_versioning import compare_project_versions, create_project_version
from hydrolite.runtime_db import list_artifact_records, list_project_version_records, list_run_records, list_warning_acknowledgment_records
from hydrolite.runtime_paths import get_project_runtime_dir
from hydrolite.scenario_registry import get_scenario
from hydrolite.ui.components.artifact_list import render_artifact_list
from hydrolite.ui.components.metric_card import render_metric_card
from hydrolite.ui.components.warning_panel import warning_payload
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
    tabs = st.tabs(["Overview", "Data", "Scenarios", "Runs", "Results", "Reports", "Delivery"])
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
    with tabs[6]:
        st.subheader("Project Delivery / 项目交付")
        st.caption("交付审核状态与科学验证状态彼此独立；Approved for Delivery 不代表 scientifically validated。")
        if not context.project_loaded:
            st.info("No versions / No deliverables / No reports. 请先加载项目。")
            return
        versions = sorted(list_project_version_records(project_id=context.project_id), key=lambda row: int(row.get("version_number") or 0))
        st.markdown("**Current Working Version / 当前工作副本**")
        st.write(f"`{context.project_name}` 可继续编辑；已冻结版本不会随工作副本静默变化。")
        if st.button("Create Version / 创建版本", key="delivery_create_version"):
            try:
                version = create_project_version(context.project_dir, created_by="local_ui", description="Created from Project Dashboard")
                st.success(f"Project Version {version['version_number']} created: {version['project_version_id']}")
                st.rerun()
            except Exception as exc: st.error(str(exc))
        if versions:
            st.dataframe(pd.DataFrame(versions), use_container_width=True, hide_index=True)
            if len(versions) > 1:
                left, right = st.columns(2)
                left_id = left.selectbox("Left version", [row["project_version_id"] for row in versions], key="version_left")
                right_id = right.selectbox("Right version", [row["project_version_id"] for row in versions], index=len(versions) - 1, key="version_right")
                st.json(compare_project_versions(left_id, right_id))
        else:
            st.info("No versions. 创建版本后才可进入正式交付流程。")

        st.divider(); st.markdown("**Deliverables / 交付物**")
        project_deliverables = list_deliverables(context.project_id)
        completed_runs = [row for row in list_run_records(project_id=context.project_id) if row.get("status") in {"success", "succeeded", "completed"} and not row.get("legacy_unversioned", True)]
        reports = [row for row in artifacts if row.get("artifact_type") == "report"]
        if versions and st.button("Create Draft Deliverable / 创建草稿交付物", key="create_draft_deliverable"):
            try:
                version = versions[-1]
                linked_runs = [row["run_id"] for row in completed_runs if row.get("project_version_id") == version["project_version_id"]]
                linked_artifacts = [row["artifact_id"] for row in artifacts if row.get("run_id") in linked_runs]
                linked_reports = [row["artifact_id"] for row in reports if row.get("run_id") in linked_runs]
                result = create_deliverable(
                    version["project_version_id"], run_ids=linked_runs, artifact_ids=linked_artifacts,
                    report_ids=linked_reports, created_by="local_ui", limitations=["Project-specific scientific limitations must be reviewed."],
                )
                st.success(f"Draft created: {result['deliverable_id']}"); st.rerun()
            except Exception as exc: st.error(str(exc))
        if not project_deliverables:
            st.info("No deliverables. 需要已关联 Project Version 的完成 Run 和报告。")
        else:
            st.dataframe(pd.DataFrame(project_deliverables), use_container_width=True, hide_index=True)
            selected_id = st.selectbox("Deliverable", [row["deliverable_id"] for row in project_deliverables], key="delivery_selected")
            selected = next(row for row in project_deliverables if row["deliverable_id"] == selected_id)
            scientific, delivery = st.columns(2)
            scientific.metric("Scientific Validation / 科学验证", selected["scientific_validation_level"])
            delivery.metric("Delivery Review / 交付审核", selected["review_status"])
            readiness = assess_delivery_readiness(selected_id)
            st.markdown("**Delivery Readiness Checklist**"); st.json(readiness)
            comment = st.text_area("Review comment / 审核意见（每次动作必填）", key="delivery_comment")
            actions = st.columns(5)
            callbacks = (
                ("Submit", submit_delivery), ("Review", review_delivery),
                ("Request Changes", request_delivery_changes), ("Approve for Delivery", approve_delivery),
                ("Reject", reject_delivery),
            )
            for column, (label, callback) in zip(actions, callbacks):
                if column.button(label, key=f"delivery_{label}"):
                    try:
                        if not comment.strip(): raise ValueError("Review comment is required")
                        callback(selected_id, actor="local_ui", comment=comment)
                        st.success(f"{label} completed"); st.rerun()
                    except Exception as exc: st.error(str(exc))
            st.markdown("**Warning Review / 警告确认**")
            acknowledgments = {row["warning_code"] for row in list_warning_acknowledgment_records(deliverable_id=selected_id)}
            for value in selected.get("warnings", []):
                code = str(value.get("warning_code") or value.get("code")) if isinstance(value, dict) else str(value)
                details = warning_payload(code)
                status = "acknowledged" if code in acknowledgments else "requires review"
                st.write(f"- `{code}`: {details['meaning']}；影响：{details['impact']}；状态：{status}。Acknowledged 不等于问题已解决。")
                if code not in acknowledgments and st.button(f"Acknowledge {code}", key=f"ack_{selected_id}_{code}"):
                    try:
                        if not comment.strip(): raise ValueError("Acknowledgment comment is required")
                        acknowledge_warning(selected_id, code, actor="local_ui", comment=comment); st.rerun()
                    except Exception as exc: st.error(str(exc))
            st.markdown("**Package Export**")
            st.write("Included: manifests, validation summary, selected reports/figures/maps/tables. Excluded: runtime DB, logs, credentials, raw data, weights, DSS/HDF5, cache.")
            export_actions = st.columns(3)
            if export_actions[0].button("Create Delivery Bundle", key="export_delivery_bundle"):
                try: st.success(create_delivery_bundle(selected_id))
                except Exception as exc: st.error(str(exc))
            if export_actions[1].button("Create Thin Project Package", key="export_thin_project"):
                try: st.success(create_project_package(context.project_dir, mode="thin"))
                except Exception as exc: st.error(str(exc))
            if export_actions[2].button("Create Portable Project Package", key="export_portable_project"):
                try: st.success(create_project_package(context.project_dir, mode="portable"))
                except Exception as exc: st.error(str(exc))

        st.divider(); st.markdown("**Import HydroLite Project**")
        upload = st.file_uploader("Select .hydrolite-project.zip", type=["zip"], key="project_package_upload")
        if upload:
            with tempfile.TemporaryDirectory(prefix="hydrolite-import-preview-") as temporary:
                package = Path(temporary) / upload.name; package.write_bytes(upload.getvalue())
                verification = verify_project_package(package); st.json(verification)
                if verification["status"] == "passed" and st.button("Import verified package", key="import_verified_package"):
                    try: st.success(import_project_package(package, context.project_dir.parent, conflict_mode="import_as_copy"))
                    except Exception as exc: st.error(str(exc))
