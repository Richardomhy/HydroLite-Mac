from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st


def render(context) -> None:
    st.subheader("洪水易发性实验")
    st.caption("合成方法演示。默认使用 spatial block CV；随机像元划分仅用于诊断。")
    tabs = st.tabs(["数据", "条件因子", "空间划分", "基线模型", "可选强化学习", "集成", "XAI", "易发性图", "不确定性", "报告"])
    root = Path("output/flood_susceptibility")
    with tabs[3]:
        path = root / "baseline_metrics.xlsx"
        if path.exists(): st.dataframe(pd.read_excel(path), use_container_width=True)
        else: st.info("尚未运行基线实验。")
    with tabs[4]: st.info("强化学习为可选实验；未优于监督基线时状态为 no_demonstrated_value_added。")
    with tabs[6]:
        path = root / "feature_importance.xlsx"
        if path.exists(): st.dataframe(pd.read_excel(path), use_container_width=True)
        st.caption("解释表示关联，不表示因果效应。")
