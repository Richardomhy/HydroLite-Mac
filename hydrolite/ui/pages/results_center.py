from __future__ import annotations

import json
from pathlib import Path
import streamlit as st

from hydrolite.artifact_store import search_artifacts
from hydrolite.result_interpretation import interpret_result
from hydrolite.ui.components.artifact_list import render_artifact_list
from hydrolite.ui.components.warning_panel import render_warning_panel
from hydrolite.ui.state import PROJECT_ROOT, load_app_state


def _susceptibility_summary() -> tuple[dict, list[str]]:
    path = PROJECT_ROOT / "output/method_inspiration/flood_susceptibility/reports/flood_susceptibility_manifest.json"
    if not path.exists(): return {}, []
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload.get("selected_test_metrics", {})
    warnings = ["REAL_DATA_VALIDATION_MISSING"]
    if payload.get("importance_stability", {}).get("status") == "unstable": warnings.append("XAI_IMPORTANCE_UNSTABLE")
    return {"selected_model": payload.get("selected_model"), "PR_AUC": metrics.get("PR_AUC"), "Brier": metrics.get("Brier"), "spatial_stability": payload.get("spatial_stability", {}).get("status")}, warnings


def render(context) -> None:
    state = load_app_state(st.session_state)
    st.header("成果中心" if state.language == "中文" else "Results Center")
    st.caption("先看结论、可信度和限制，再查看完整模型文件。")
    metrics, warning_codes = _susceptibility_summary()
    interpretation = interpret_result(metrics, validation_status="synthetic_demo" if metrics else "not_tested", readiness="ready" if metrics else "missing", limitations=("易发性不等于风险。",), result_type="flood_susceptibility")
    try: rows = search_artifacts(context.project_id if context.project_loaded else None, state.selected_run or None, None)
    except Exception: rows = []
    tabs = st.tabs(["概览", "可信度", "不确定性", "成果文件", "报告"])
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
            st.write(f"Validation Level：{'synthetic_demo' if metrics else 'not tested'}")
            st.write(f"Model Status：{'experimental' if metrics else 'not run'}")
            st.write("Real-world validation：Not tested")
            st.write(f"Artifacts：{len(rows)}")
        for code in warning_codes: render_warning_panel(code)
        st.caption("不确定性：空间块差异、数据质量与模型选择需联合审阅。")
    with tabs[1]:
        st.write("Data Quality：按项目数据中心记录")
        st.write("Validation Level：synthetic_demo" if metrics else "Validation Level：not tested")
        st.write("Model Status：experimental" if metrics else "Model Status：not run")
        st.write("Real-world validation：Not tested")
        for code in warning_codes: render_warning_panel(code)
    with tabs[2]:
        st.write("Uncertainty：空间块差异、数据质量与模型选择不确定性必须联合审阅。")
        for limitation in interpretation.limitations: st.warning(limitation)
    with tabs[3]: render_artifact_list(rows)
    with tabs[4]:
        reports = [row for row in rows if str(row.get("artifact_type", "")).lower() == "report"]
        render_artifact_list(reports)
        if not reports: st.info("暂无关联报告。M7A 复用现有报告引擎，不执行新的正式交付审核。")
    if state.ui_mode == "advanced":
        with st.expander("完整解释结构"): st.json(interpretation.as_dict())
