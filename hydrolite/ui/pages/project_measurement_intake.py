from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.data_upload import sanitize_uploaded_filename
from hydrolite.project_measurement_intake import (
    TEMPLATES, generate_templates, list_requirements,
    review_measurement_submission,
    submit_measurement_file,
)


def render(context) -> None:
    st.header("项目实测数据补充")
    st.caption("公开数据、项目实测/调查数据、项目审批参数分别管理；上传不等于接受，也不会自动解除科学门禁。")
    if not context.project_loaded:
        st.warning("请先在项目中心打开一个已创建的项目工作区。")
        return
    project = Path(context.project_dir)
    try:
        result = list_requirements(project)
    except Exception as exc:
        st.error(f"项目存储不可用，已阻止上传：{exc}")
        return
    reqs = result["requirements"]
    counts = {
        "missing": sum(row["current_status"] in {"missing", "project_measurement_required", "unavailable"} for row in reqs),
        "submission_received": sum(row["current_status"] == "submission_received" for row in reqs),
        "validation_failed": sum(row["current_status"] == "validation_failed" for row in reqs),
        "needs_review": sum(row["current_status"] == "needs_review" for row in reqs),
        "accepted": sum(row["current_status"] == "accepted" for row in reqs),
    }
    cols = st.columns(5)
    for col, name, label in zip(cols, counts, ("Missing", "Submitted", "Invalid", "Needs Review", "Accepted")):
        col.metric(label, counts[name])
    st.dataframe(pd.DataFrame([{ "编号": r["requirement_id"], "资料": r["business_name_zh"], "当前状态": r["current_status"], "模板版本": r["template_id"], "阻塞能力": r["blocked_capability"], "所需原因": r["reason_required"]} for r in reqs]), use_container_width=True, hide_index=True)

    if st.button("生成当前补资料包", type="secondary"):
        try:
            st.session_state["measurement_pack"] = generate_templates(project)
            st.success("已生成项目补资料包。仅含空白模板和需求清单。")
        except Exception as exc:
            st.error(str(exc))
    pack = st.session_state.get("measurement_pack")
    if pack:
        for label, key, filename in (("下载补资料包", "request_pack", "project_measurement_request_pack.zip"), ("下载必需数据清单", "user_required_data", "user_required_data.xlsx")):
            path = Path(pack[key])
            if path.is_file(): st.download_button(label, path.read_bytes(), file_name=filename, key=f"measurement_{key}")

    st.subheader("上传、校验与预览")
    requirement = st.selectbox("资料类型", list(TEMPLATES), format_func=lambda key: f"{key} · {TEMPLATES[key]['title']}")
    st.caption("仅接受 CSV/XLSX，单文件最大 50 MiB；不支持宏文件。原始文件在项目工作区只读保存。")
    source_ids_text = st.text_input("项目已登记 source_id（精确匹配；逗号分隔）", help="可从工作区来源清单自动读取；未登记时需先完成 MR01 或提供正式来源编号。不会按名称自动绑定。")
    upload = st.file_uploader("选择项目实测/调查文件", type=["csv", "xlsx"], key="measurement_upload")
    sheet_name = st.text_input("Excel 工作表名称（留空使用首个数据表）", help="多工作表文件可填写要导入的工作表名称；CSV 留空即可。") if upload and upload.name.lower().endswith(".xlsx") else None
    if upload and st.button("校验并提交预览", disabled=upload.size > 50 * 1024 * 1024):
        staging = project / "measurements" / "staging" / sanitize_uploaded_filename(upload.name)
        try:
            staging.parent.mkdir(parents=True, exist_ok=True)
            staging.write_bytes(upload.getbuffer())
            source_ids = {x.strip() for x in source_ids_text.split(",") if x.strip()} or None
            submitted = submit_measurement_file(staging, project, requirement, submitter="local_user", source_ids=source_ids, sheet_name=sheet_name or None)
            st.session_state["measurement_submission"] = submitted
        except Exception as exc:
            st.error(str(exc))
        finally:
            staging.unlink(missing_ok=True)
    submitted = st.session_state.get("measurement_submission")
    if submitted:
        if submitted.get("status") == "duplicate_submission":
            st.info("发现 SHA-256 完全重复的文件；未重复导入。")
        else:
            st.write(f"Submission `{submitted['submission_id']}` · 状态 `{submitted['status']}` · 校验 `{submitted['validation']['status']}`")
            preview = submitted["validation"].get("preview", [])
            if preview: st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)
            errors = submitted["validation"].get("errors", [])
            if errors: st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)
            if submitted.get("status") == "needs_review":
                reviewer = st.text_input("本地审核人", value="local_user", key="measurement_reviewer")
                comment = st.text_area("审核意见（必填）", key="measurement_review_comment")
                action = st.radio("审核动作", ["keep_unresolved", "accept", "reject"], format_func=lambda value: {"keep_unresolved": "保持待确认", "accept": "接受并登记", "reject": "拒绝"}[value], horizontal=True)
                if st.button("记录审核", disabled=not comment.strip() or not reviewer.strip()):
                    try:
                        audit = review_measurement_submission(project, submitted["submission_id"], action, reviewer=reviewer, comment=comment)
                        st.session_state["measurement_review_result"] = {"audit": audit, "refresh": audit.get("gate_refresh")}
                        st.success("审核已记录；接受后已自动刷新需求解析和现有门禁。门禁不能人工置为 ready。")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"未完成审核/导入：{exc}")
    review_result = st.session_state.get("measurement_review_result")
    if review_result: st.json(review_result)
    st.caption("受纳河段、坐标基准和项目系数必须保留人工证据；nearest reach 不会自动确认。审核接受只会触发既有 resolver/gate 流程，不会启动 M9B。")
