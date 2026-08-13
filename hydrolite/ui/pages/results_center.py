from __future__ import annotations

import json
from pathlib import Path
import streamlit as st

from hydrolite.artifact_store import search_artifacts
from hydrolite.delivery_review import list_deliverables
from hydrolite.integrity_verification import verify_deliverable
from hydrolite.result_interpretation import interpret_result
from hydrolite.ui.components.artifact_list import render_artifact_list
from hydrolite.ui.components.warning_panel import render_warning_panel
from hydrolite.ui.pages.real_project_baseline import build_real_project_summary, find_real_project_baseline, load_real_project_manifest
from hydrolite.ui.state import PROJECT_ROOT, load_app_state


def _susceptibility_summary() -> tuple[dict, list[str]]:
    path = PROJECT_ROOT / "output/method_inspiration/flood_susceptibility/reports/flood_susceptibility_manifest.json"
    if not path.exists(): return {}, []
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload.get("selected_test_metrics", {})
    warnings = ["REAL_DATA_VALIDATION_MISSING"]
    if payload.get("importance_stability", {}).get("status") == "unstable": warnings.append("XAI_IMPORTANCE_UNSTABLE")
    return {"selected_model": payload.get("selected_model"), "PR_AUC": metrics.get("PR_AUC"), "Brier": metrics.get("Brier"), "spatial_stability": payload.get("spatial_stability", {}).get("status")}, warnings


def _real_m8b_payload(context) -> tuple[dict, dict] | None:
    project = context.project.get("project", context.project) if isinstance(context.project, dict) else {}
    if not project.get("real_project"):
        return None
    root = find_real_project_baseline(context)
    if not (root / "m8b/reports/m8b_manifest.json").is_file():
        return None
    manifest = load_real_project_manifest(root)
    return manifest, build_real_project_summary(manifest)


def render(context) -> None:
    state = load_app_state(st.session_state)
    st.header("成果中心" if state.language == "中文" else "Results Center")
    st.caption("先看结论、可信度和限制，再查看完整模型文件。")
    real_payload = _real_m8b_payload(context)
    if real_payload:
        manifest, summary = real_payload
        metrics = {key: value for key, value in summary.items() if value != "unavailable"}
        warning_codes = []
        warning_messages = [str(item) for item in manifest.get("warnings", [])]
        validation_status = summary["Scientific Validation"]
        model_status = "actual_hydrolite_run"
        readiness = manifest.get("water_environment_hydrology_gate", "ready_with_warnings")
        limitations = tuple(map(str, manifest.get("limitations", [])))
        result_type = "real_project_hydrology"
    else:
        metrics, warning_codes = _susceptibility_summary()
        warning_messages = []
        validation_status = "synthetic_demo" if metrics else "not_tested"
        model_status = "experimental" if metrics else "not run"
        readiness = "ready" if metrics else "missing"
        limitations = ("易发性不等于风险。",)
        result_type = "flood_susceptibility"
    interpretation = interpret_result(metrics, validation_status=validation_status, readiness=readiness, limitations=limitations, result_type=result_type)
    try: rows = search_artifacts(context.project_id if context.project_loaded else None, state.selected_run or None, None)
    except Exception: rows = []
    tabs = st.tabs(["概览", "可信度", "不确定性", "Working Results", "报告", "Frozen Deliverables"])
    with tabs[0]:
        st.subheader(interpretation.headline); st.write(interpretation.summary)
        findings, trust = st.columns(2)
        with findings:
            st.markdown("**Key Findings / 关键指标**")
            if interpretation.key_findings:
                for finding in interpretation.key_findings: st.write(f"- {finding}")
            else: st.info("尚无结果。请先在场景中心完成一次运行。")
        with trust:
            st.markdown("**Validation / 可信度**")
            st.write(f"Validation Level：{validation_status}")
            st.write(f"Model Status：{model_status}")
            st.write(f"Real-world validation：{validation_status}")
            st.write(f"Artifacts：{len(rows)}")
        for code in warning_codes: render_warning_panel(code)
        for warning in warning_messages: st.warning(warning)
        st.caption("不确定性：请结合数据质量、参数来源和验证等级审阅。" if real_payload else "不确定性：空间块差异、数据质量与模型选择需联合审阅。")
    with tabs[1]:
        st.write("Data Quality：按项目数据中心记录")
        st.write(f"Validation Level：{validation_status}")
        st.write(f"Model Status：{model_status}")
        st.write(f"Real-world validation：{validation_status}")
        for code in warning_codes: render_warning_panel(code)
    with tabs[2]:
        st.write("Uncertainty：真实项目结果必须联合数据质量、参数来源、事件数和验证分组审阅。" if real_payload else "Uncertainty：空间块差异、数据质量与模型选择不确定性必须联合审阅。")
        for warning in warning_messages: st.warning(warning)
        for limitation in interpretation.limitations: st.warning(limitation)
    with tabs[3]: render_artifact_list(rows)
    with tabs[4]:
        reports = [row for row in rows if str(row.get("artifact_type", "")).lower() == "report"]
        render_artifact_list(reports)
        if not reports: st.info("暂无关联报告。")
    with tabs[5]:
        frozen = [row for row in list_deliverables(context.project_id if context.project_loaded else None) if row.get("review_status") == "approved_for_delivery"]
        if not frozen:
            st.info("No frozen deliverables. 已批准交付物将在这里显示固定 manifest、hash、审核和警告。")
        for item in frozen:
            st.markdown(f"### Frozen: {item['deliverable_id']}")
            scientific, delivery = st.columns(2)
            scientific.write(f"Scientific Validation: `{item['scientific_validation_level']}`")
            delivery.write(f"Delivery Review: `{item['review_status']}`")
            st.write(f"Manifest hash: `{item.get('manifest_hash') or 'missing'}`")
            st.write("Warnings:", item.get("warnings", [])); st.write("Limitations:", item.get("limitations", []))
            st.json(verify_deliverable(item["deliverable_id"]))
    if state.ui_mode == "advanced":
        with st.expander("完整解释结构"): st.json(interpretation.as_dict())
