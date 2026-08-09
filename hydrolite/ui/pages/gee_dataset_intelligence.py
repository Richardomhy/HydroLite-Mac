from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st

from hydrolite.gee.auth import get_gee_status
from hydrolite.gee_catalog import catalog_status, compare_datasets, generate_ee_code, get_catalog_dataset, recommend_datasets, search_catalog
from hydrolite.gee_catalog.transport import detect_available_transports
from hydrolite.ui.components.warning_panel import render_warning_panel


def gee_product_status() -> dict:
    catalog = catalog_status(); compute = get_gee_status(); transport = detect_available_transports()
    compute_init = compute.get("initialization", {}) if isinstance(compute, dict) else {}
    transport_status = catalog.get("catalog_transport")
    if not transport_status:
        transport_status = "available" if any(item.get("available") for item in transport) else "unavailable"
    return {
        "catalog_source": "Official Earth Engine STAC",
        "catalog_status": catalog.get("status", "unavailable"),
        "record_count": catalog.get("record_count", catalog.get("records", 0)),
        "compute_auth_status": compute_init.get("status", "unavailable"),
        "catalog_transport_status": transport_status,
    }


def render(context) -> None:
    st.header("GEE Dataset Intelligence")
    status = gee_product_status(); st.json(status)
    if status["compute_auth_status"] not in {"available", "passed", "initialized"}: render_warning_panel("GEE_COMPUTE_AUTH_UNAVAILABLE")
    st.caption("目录状态与计算认证相互独立：认证失败不会让离线官方目录变成不可用。")
    tabs = st.tabs(["Catalog Status", "Search", "Dataset Detail", "Compare", "Recommend", "Code", "Refresh"])
    query_result = None
    with tabs[0]: st.json(catalog_status())
    with tabs[1]:
        query = st.text_input("关键词 / Asset ID", value="precipitation")
        query_result = search_catalog(query) if query else {"matches": []}
        st.dataframe(pd.DataFrame(query_result.get("matches", [])), use_container_width=True, hide_index=True)
        if query_result.get("status") == "no_exact_match": st.info("没有完全匹配；放宽条件建议会单独列出，不会静默删除限制。")
    asset_ids = [row.get("asset_id") for row in (query_result or {}).get("matches", []) if row.get("asset_id")]
    with tabs[2]:
        asset = st.text_input("Asset ID", value=asset_ids[0] if asset_ids else "USGS/SRTMGL1_003")
        st.json(get_catalog_dataset(asset) or {"status": "not_found"})
    with tabs[3]:
        selected = st.multiselect("选择数据集", asset_ids, default=asset_ids[:2])
        if selected: st.json(compare_datasets(selected))
        else: st.info("请先搜索并选择至少一个数据集。")
    with tabs[4]:
        use_case = st.selectbox("场景", ["watershed_delineation", "continuous_hydrology", "drought_forecast", "flood_susceptibility"])
        st.json(recommend_datasets(use_case))
    with tabs[5]:
        code_asset = st.text_input("代码 Asset ID", value="USGS/SRTMGL1_003")
        st.code(generate_ee_code(code_asset).get("code", "Authentication required for execution."), language="python")
    with tabs[6]:
        st.info("目录刷新是显式高级操作；首页不会触发 refresh。请通过 CLI 使用 dry-run/execute。")
        report = Path("output/gee_catalog_intelligence/gee_catalog_report_zh.md")
        if report.exists(): st.download_button("下载目录报告", report.read_bytes(), file_name=report.name)
