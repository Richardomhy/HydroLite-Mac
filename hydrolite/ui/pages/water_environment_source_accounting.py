from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.ui.state import PROJECT_ROOT


DEFAULT_OUTPUT = PROJECT_ROOT / "output/water_environment/m9a"


def read_water_environment_outputs(output_dir: str | Path = DEFAULT_OUTPUT) -> dict:
    root = Path(output_dir)
    manifest_path = root / "reports/m9a_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    return {
        "root": root,
        "manifest": manifest,
        "inventory": root / "inventory/pollution_source_inventory.xlsx",
        "factors": root / "factors/emission_factor_audit.xlsx",
        "ledger": root / "ledger/source_load_ledger.xlsx",
        "coverage": root / "summary/coverage_summary.xlsx",
        "report": root / "reports/m9a_water_environment_source_accounting_report_zh.md",
    }


def _show_table(path: Path, sheet_name: str | int = 0) -> None:
    if not path.is_file(): st.info("尚无该类成果。")
    else:
        frame = pd.read_excel(path, sheet_name=sheet_name).head(200)
        for column in frame.select_dtypes(include="object"):
            frame[column] = frame[column].astype("string")
        st.dataframe(frame, width="stretch", hide_index=True)


def render(context) -> None:
    st.header("Water Environment Source Accounting")
    st.caption("Experimental / Foundation · M9A · source_accounting_only")
    st.warning("当前水环境能力仅完成污染源清单和产生/净排放负荷核算，尚未模拟污染物入河输移和河流水质过程。")
    render_point_source_closure()
    render_evidence_completion()
    outputs = read_water_environment_outputs()
    if not outputs["manifest"]:
        st.info("尚无 M9A 成果。首次运行需在本地 CLI 显式提供只读真实项目源路径。")
        st.code("python -m hydrolite water-environment inventory --source-root <real-project-source>")
        return
    manifest = outputs["manifest"]
    st.write({
        "source_inventory_validation": manifest.get("source_inventory_validation"),
        "source_load_accounting_validation": manifest.get("source_load_accounting_validation"),
        "water_quality": manifest.get("water_quality"),
        "pollutant_delivery_model_gate": manifest.get("pollutant_delivery_model_gate"),
    })
    tabs = st.tabs(["Sources", "Factors", "Ledger", "Coverage", "Evidence", "Limitations"])
    with tabs[0]: _show_table(outputs["inventory"], "inventory")
    with tabs[1]: _show_table(outputs["factors"], "project_factor_readiness")
    with tabs[2]: _show_table(outputs["ledger"], "source_load_ledger")
    with tabs[3]: _show_table(outputs["coverage"], "coverage")
    with tabs[4]: st.json({"factor_sources": manifest.get("factor_sources"), "evidence_tiers": manifest.get("evidence_tiers"), "data_snapshot_id": manifest.get("data_snapshot_id")})
    with tabs[5]:
        for limitation in manifest.get("limitations", []): st.warning(limitation)
        if outputs["report"].is_file(): st.download_button("下载 M9A 中文报告", outputs["report"].read_bytes(), file_name=outputs["report"].name)


def render_evidence_completion(output_dir=None):
    from hydrolite.source_evidence_workflow import DEFAULT_OUTPUT as EVIDENCE_OUTPUT, read_evidence_state, record_review, run_evidence_closure
    root = Path(output_dir or EVIDENCE_OUTPUT)
    state = read_evidence_state(root)
    st.subheader("M9A.1 Evidence / Readiness")
    if not state:
        st.info("尚无证据闭环成果；本地运行 water-environment evidence --source-root <资料目录>。")
        return
    if state.get("outputs_stale"): st.warning("审批状态已变化，需重新计算 Readiness；已有冻结版本不会改变。")
    tabs = st.tabs(["Evidence Review", "Factor Approval", "Spatial Mapping", "Readiness"])
    with tabs[0]:
        _show_table(root / "evidence/evidence_review_queue.xlsx")
        items = state.get("evidence", [])
        if items:
            labels = {e["evidence_id"]: f"{e['source_id'] or '待关联来源'} · {e['field_name'] or e['evidence_type']} · {e['status']}" for e in items}
            choice = st.selectbox("Evidence", list(labels), format_func=labels.get, key=str(root) + "evidence")
            item = next(e for e in items if e["evidence_id"] == choice)
            st.json(item)
            with st.form(str(root) + "evidence_review"):
                actor = st.text_input("Reviewer")
                comment = st.text_area("Comment")
                action = st.selectbox("Decision", ["confirm", "reject", "keep_unresolved"])
                if st.form_submit_button("保存证据审核"):
                    try: record_review(root, choice, action, actor=actor, comment=comment); st.success("已保存，待重新计算。")
                    except (ValueError, OSError) as exc: st.error(str(exc))
    with tabs[1]:
        items = state.get("factors", [])
        st.warning("项目批准仅表示本项目采用，不代表普遍正确；示例和 export/delivery 系数不能批准。")
        if items:
            choice = st.selectbox("Factor", [f["factor_id"] for f in items], key=str(root) + "factor")
            st.json(next(f for f in items if f["factor_id"] == choice))
            with st.form(str(root) + "factor_review"):
                actor = st.text_input("Approver")
                comment = st.text_area("Approval comment")
                action = st.selectbox("Factor decision", ["reviewed", "approved_for_project", "rejected", "superseded"])
                if st.form_submit_button("保存系数决定"):
                    try: record_review(root, choice, action, actor=actor, comment=comment, factor=True); st.success("已保存，待重新计算。")
                    except (ValueError, OSError) as exc: st.error(str(exc))
    with tabs[2]: _show_table(root / "spatial/source_reach_mapping.xlsx")
    with tabs[3]:
        _show_table(root / "activity/activity_gap_matrix.xlsx")
        _show_table(root / "factors/factor_gap_matrix.xlsx")
        _show_table(root / "readiness/m9b_readiness.xlsx")
        if st.button("重新计算 Readiness", key=str(root) + "rebuild"):
            try:
                if (root / "reports/m9a2_manifest.json").is_file():
                    from hydrolite.point_source_workflow import run_point_source_closure
                    st.json(run_point_source_closure(output_dir=root)["gates"])
                else: st.json(run_evidence_closure(output_dir=root)["pollutant_delivery_model_gate"])
            except (ValueError, OSError) as exc: st.error(str(exc))
        request = root / "readiness/m9a1_data_request_list.xlsx"
        if request.is_file(): st.download_button("下载补资料清单", request.read_bytes(), file_name=request.name)


def render_point_source_closure(output_dir=None):
    from hydrolite.point_source_workflow import DEFAULT_OUTPUT as POINT_OUTPUT
    root = Path(output_dir or POINT_OUTPUT)
    st.subheader("Point Source Closure / 点源证据闭环")
    manifest = root / "reports/m9a2_manifest.json"
    if not manifest.is_file():
        st.info("本地运行 water-environment point-source-status 生成点源审计。")
        return
    facts = json.loads(manifest.read_text(encoding="utf-8"))
    st.json({k: facts["gates"][k] for k in ("point_source_m9b_eligibility", "point_source_delivery_gate", "diffuse_source_delivery_gate", "pollutant_delivery_model_gate")})
    st.warning("坐标数值范围不代表 CRS 已确认；点源资格不能代表全流域；不会自动批准系数。")
    tabs = st.tabs(["Identity", "Spatial", "Flow", "Concentration", "Factor", "Load", "Readiness"])
    files = ["identity/point_source_identity_audit.xlsx", "spatial/source_reach_review_queue.xlsx", "flow/source_flow_evidence.xlsx", "concentration/source_concentration_audit.xlsx", "factors/factor_decision_pack.xlsx", "load/point_source_load_ledger_v3.xlsx", "readiness/point_source_readiness.xlsx"]
    for tab, name in zip(tabs, files):
        with tab: _show_table(root / name)
    with st.expander("Review Evidence / Confirm Mapping / Review Factor"):
        if facts.get("project_version"):
            st.info("此版本已冻结。先在新的输出目录建立修订工作副本，再逐项审核；不改写已交付版本。")
        else: render_evidence_completion(root)
    for name in ("m9a2_project_data_request_pack.xlsx", "m9a2_point_source_data_template.xlsx"):
        path = root / "requests" / name
        if path.is_file(): st.download_button(name, path.read_bytes(), file_name=name)
