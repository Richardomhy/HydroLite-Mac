from __future__ import annotations

from pathlib import Path
import streamlit as st

from hydrolite.gee_catalog import catalog_status, search_catalog


def render(context) -> None:
    st.subheader("GEE 数据集智能目录")
    st.caption("离线目录可查询；实际 Earth Engine 计算和导出仍需本地认证。")
    st.json(catalog_status())
    query = st.text_input("关键词 / Asset ID", value="precipitation")
    if query: st.dataframe(search_catalog(query)["matches"], use_container_width=True)
    report = Path("output/gee_catalog_intelligence/gee_catalog_report_zh.md")
    if report.exists(): st.download_button("下载目录报告", report.read_bytes(), file_name=report.name)
