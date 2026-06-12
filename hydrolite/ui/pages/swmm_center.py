from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.config import load_case
from hydrolite.project import run_project_case
from hydrolite.ui.components import read_swmm_outputs, show_download, show_dataframe
from hydrolite.ui.state import WorkbenchContext


def _swmm_cases(context: WorkbenchContext) -> list[str]:
    names = []
    for case_name in context.cases:
        try:
            if load_case(context.project_dir / "cases" / case_name).swmm_enabled:
                names.append(case_name)
        except Exception:
            continue
    return names


def render(context: WorkbenchContext) -> None:
    st.header("SWMM 联动")
    st.caption("查看 HydroLite 到 SWMM 入流联动、SWMM 结果和关键过程线。")
    if not context.project_loaded:
        st.error(context.error_message)
        return
    cases = _swmm_cases(context)
    if not cases:
        st.info("当前项目没有启用 SWMM 的情景。")
        return

    selected = st.selectbox("当前 SWMM 情景", cases)
    case_stem = Path(selected).stem
    swmm_dir = context.project_dir / "output" / case_stem / "swmm"
    if st.button("运行 SWMM 情景", use_container_width=True):
        with st.spinner(f"正在运行 {selected}..."):
            outputs = run_project_case(context.project_dir, selected)
        st.success(f"运行完成: `{outputs.output_dir}`")

    tables = read_swmm_outputs(swmm_dir)
    for key, title in [
        ("summary", "swmm_summary"),
        ("kpis", "swmm_kpis"),
        ("coupling", "coupling_summary"),
        ("system", "system_timeseries"),
    ]:
        if key in tables:
            show_dataframe(title, tables[key])
    if "node_depth" in tables:
        node = tables["node_depth"]
        show_dataframe("node_depth_timeseries", node)
        if {"node_id", "depth"}.issubset(node.columns):
            st.bar_chart(node.groupby("node_id")["depth"].max())
    if "link_flow" in tables:
        link = tables["link_flow"]
        show_dataframe("link_flow_timeseries", link)
        if {"link_id", "flow"}.issubset(link.columns):
            st.bar_chart(link.groupby("link_id")["flow"].max())

    for path, label, mime in [
        (swmm_dir / "swmm_summary.xlsx", "下载 swmm_summary.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        (swmm_dir / "swmm_kpis.xlsx", "下载 swmm_kpis.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        (swmm_dir / "coupling_summary.xlsx", "下载 coupling_summary.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        (swmm_dir / "node_depth_timeseries.csv", "下载 node_depth_timeseries.csv", "text/csv"),
        (swmm_dir / "link_flow_timeseries.csv", "下载 link_flow_timeseries.csv", "text/csv"),
        (swmm_dir / "system_timeseries.csv", "下载 system_timeseries.csv", "text/csv"),
    ]:
        show_download(label, path, mime)
