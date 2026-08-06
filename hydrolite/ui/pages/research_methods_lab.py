from __future__ import annotations

import streamlit as st

from hydrolite.research_registry import NOTICE, built_in_sources


def render(context) -> None:
    st.subheader("水文环境方法实验室")
    st.warning("借鉴论文方法不等于复现论文模型。")
    st.caption(NOTICE)
    tabs = st.tabs(["来源登记", "许可", "方法卡", "Gamma 滞后", "河网图结构", "图时序残差", "趋势感知", "多提前期", "水质实验", "基准比较", "数据泄漏", "报告"])
    with tabs[0]: st.dataframe(built_in_sources(), use_container_width=True)
    with tabs[1]: st.info("第三方 GEE Skill：license_file_missing，仅以 clean-room 方法借鉴方式登记。")
    with tabs[5]: st.warning("双向模型只能用于历史分析，不能用于真正的未来预测。")
    with tabs[8]: st.info("water_quality 主能力仍为 planned；本页仅展示方法与数据接口。")
