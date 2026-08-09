from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.product_status import get_product_feature_status
from hydrolite.research_intake import list_methods, list_sources
from hydrolite.research_registry import NOTICE
from hydrolite.ui.components.warning_panel import render_experimental_gate


def _method_rows() -> list[dict]:
    return [{
        "method_id": item.method_id, "source_ids": ", ".join(item.source_ids),
        "current_status": item.current_status, "implementation_mode": item.recommended_integration_mode,
        "borrowed_concepts": ", ".join(item.borrowed_concepts), "not_copied": ", ".join(item.not_to_copy),
        "synthetic_evidence": item.synthetic_value_added or item.value_added_gate,
        "real_data_evidence": item.real_data_value_added or "not_tested", "next_step": item.next_milestone,
    } for item in list_methods()]


def render(context) -> None:
    st.header("方法实验室")
    render_experimental_gate()
    st.error("Method inspired ≠ paper reproduction. 方法借鉴不等于论文模型复现。")
    st.caption(NOTICE)
    tabs = st.tabs(["Overview", "Research Sources", "Method Cards", "Gamma", "Graph & Trend", "Water Quality Lab", "Flood Susceptibility", "Benchmarks", "Limitations"])
    with tabs[0]:
        st.write("本页只查看和运行已有实验接口，不新增算法。")
        st.dataframe(pd.DataFrame(_method_rows())[["method_id", "current_status", "synthetic_evidence", "real_data_evidence"]], use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(pd.DataFrame([item.as_dict() for item in list_sources()]), use_container_width=True, hide_index=True)
        st.info("第三方 GEE Skill：license_file_missing，仅允许 clean-room 独立实现。")
    with tabs[2]: st.dataframe(pd.DataFrame(_method_rows()), use_container_width=True, hide_index=True)
    with tabs[3]:
        status = get_product_feature_status("gamma_lag_features"); st.json(status.as_dict())
    with tabs[4]:
        for feature in ("river_graph_features", "trend_aware_features", "multihorizon_forecast"):
            st.json(get_product_feature_status(feature).as_dict())
        st.warning("Trend synthetic value-added not demonstrated，不能默认推荐。双向模型只能用于历史分析。")
    with tabs[5]:
        st.json(get_product_feature_status("water_quality_method_lab").as_dict())
        st.warning("water_quality 主能力仍为 planned。")
    with tabs[6]:
        st.json(get_product_feature_status("flood_susceptibility").as_dict())
        st.json(get_product_feature_status("flood_susceptibility_xai").as_dict())
        st.write("Recommended model：Logistic Regression。复杂模型未证明有足够 validation improvement。")
    with tabs[7]:
        st.write("M5：Hydrology 12/16；Graph 13/16；Gamma 1/16；Trend 0/16；overall mixed。")
        st.warning("所有 real-data value-added 均为 not tested。")
    with tabs[8]:
        st.write("Synthetic Demo 不能替代真实项目独立验证；数据驱动方法不能替代 HydroLite 水量账本；XAI 不表示因果关系。")
