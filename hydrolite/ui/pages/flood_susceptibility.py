from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import streamlit as st

from hydrolite.ui.components.warning_panel import render_experimental_gate, render_warning_panel
from hydrolite.ui.state import PROJECT_ROOT


ROOT = PROJECT_ROOT / "output/method_inspiration/flood_susceptibility"


def _read_excel(relative: str) -> pd.DataFrame:
    path = ROOT / relative
    try: return pd.read_excel(path) if path.exists() else pd.DataFrame()
    except Exception: return pd.DataFrame()


def load_flood_susceptibility_ui_status(root: Path = ROOT) -> dict:
    path = root / "reports/flood_susceptibility_manifest.json"
    if not path.exists(): return {"status": "not_run", "rl_suitability": "rl_not_justified", "real_data_value_added": "not_tested"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "status": payload.get("status"), "validation_level": payload.get("validation_level"),
        "selected_model": payload.get("selected_model"), "selection_reason": payload.get("selection", {}).get("selection_reason"),
        "complex_model_value_added": payload.get("complex_model_value_added"),
        "spatial_stability": payload.get("spatial_stability", {}).get("status"),
        "xai_importance_stability": payload.get("importance_stability", {}).get("status"),
        "rl_suitability": payload.get("rl_suitability", {}).get("status", "rl_not_justified"),
        "real_data_value_added": payload.get("real_data_value_added", "not_tested"),
    }


def render(context) -> None:
    st.header("洪水易发性制图")
    render_experimental_gate()
    st.error("Susceptibility ≠ Risk：易发性不等于风险；本阶段不计算暴露度、脆弱性和后果。")
    status = load_flood_susceptibility_ui_status(); st.json(status)
    if status.get("xai_importance_stability") == "unstable": render_warning_panel("XAI_IMPORTANCE_UNSTABLE")
    st.info("RL suitability：rl_not_justified。M7A 不提供不存在的 RL 运行按钮。")
    st.info("推荐模型：Logistic Regression。复杂模型 value-added 未得到证明，不会因复杂度更高而默认突出。")
    tabs = st.tabs(["Data", "Spatial Validation", "Models", "Map", "XAI", "Limitations"])
    with tabs[0]:
        frame = _read_excel("data_quality/inventory_qc.xlsx")
        if frame.empty: st.info("尚无清单 QC 结果。")
        else: st.dataframe(frame, use_container_width=True, hide_index=True)
    with tabs[1]:
        frame = _read_excel("spatial_validation/block_metrics.xlsx")
        if frame.empty: st.info("尚无空间验证结果。")
        else: st.dataframe(frame, use_container_width=True, hide_index=True)
    with tabs[2]:
        frame = _read_excel("models/model_metrics.xlsx")
        if frame.empty: st.info("尚无模型结果。")
        else: st.dataframe(frame, use_container_width=True, hide_index=True)
    with tabs[3]:
        image = ROOT / "charts/susceptibility_map.png"
        if image.exists(): st.image(str(image), caption="Relative flood susceptibility · SYNTHETIC DEMO")
        else: st.info("尚无易发性图。")
    with tabs[4]:
        frame = _read_excel("xai/global_importance.xlsx")
        if frame.empty: st.info("尚无解释结果。")
        else: st.dataframe(frame, use_container_width=True, hide_index=True)
        st.caption("Feature importance 表示模型关联，不表示因果效应。")
    with tabs[5]:
        st.write("Validation：Synthetic spatial validation")
        st.write(f"Spatial stability：{status.get('spatial_stability', 'not tested')}")
        st.write(f"XAI stability：{status.get('xai_importance_stability', 'not tested')}")
        st.write("Real-world validation：Not tested")
