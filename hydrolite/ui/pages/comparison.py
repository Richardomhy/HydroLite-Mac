from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.project import compare_project_outputs
from hydrolite.ui.components import read_comparison_outputs, show_download
from hydrolite.ui.state import WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("结果对比")
    st.caption("对比多个情景的 HydroLite、SWMM、coupling 与观测评估指标。")
    if not context.project_loaded:
        st.error(context.error_message)
        return

    if st.button("生成项目对比", use_container_width=True):
        with st.spinner("正在生成项目情景对比..."):
            outputs = compare_project_outputs(context.project_dir)
        st.success(f"项目对比已生成: `{outputs.xlsx}`")

    outputs = read_comparison_outputs(context.project_dir / "output")
    if not outputs:
        st.info("暂无 comparison 输出。")
        return

    for key in (
        "overview",
        "hydrology_metrics",
        "water_balance_metrics",
        "swmm_metrics",
        "coupling_metrics",
        "performance_metrics",
    ):
        df = outputs.get(key)
        if isinstance(df, pd.DataFrame):
            st.subheader(key)
            st.dataframe(df, use_container_width=True)

    for key, caption in [
        ("peak_flow_png", "peak_flow_comparison.png"),
        ("volume_png", "volume_comparison.png"),
        ("water_balance_png", "water_balance_comparison.png"),
        ("swmm_kpi_png", "swmm_kpi_comparison.png"),
    ]:
        path = outputs.get(key)
        if isinstance(path, Path):
            st.image(str(path), caption=caption)

    for key, label, mime in [
        ("scenario_comparison_xlsx", "下载 scenario_comparison.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("scenario_comparison_csv", "下载 scenario_comparison.csv", "text/csv"),
        ("hydrolite_report_md", "下载 hydrolite_report.md", "text/markdown"),
    ]:
        path = outputs.get(key)
        if isinstance(path, Path):
            show_download(label, path, mime)
