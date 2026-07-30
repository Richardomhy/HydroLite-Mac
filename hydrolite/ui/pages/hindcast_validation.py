from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.hindcast import DEFAULT_OUTPUT, DEMO_SOURCE, prepare_hindcast_workspace, run_hydrolite_hindcast_batch, summarize_hindcast_validation
from hydrolite.data_assimilation import run_assimilation_batch
from hydrolite.lead_time_validation import run_lead_time_validation
from hydrolite.validation_readiness import assess_hindcast_readiness


def _table(path: Path, sheet_name: str | int = 0) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_excel(path, sheet_name=sheet_name) if path.suffix == ".xlsx" else pd.read_csv(path)


def _show(path: Path, sheet_name: str | int = 0) -> None:
    frame = _table(path, sheet_name)
    if frame.empty:
        st.info(f"尚无结果：{path.name}")
    else:
        st.dataframe(frame, use_container_width=True)


def render(context) -> None:
    st.header("历史洪水验证")
    st.warning("数据同化使用了同化时刻的观测，analysis 结果不能与纯预报结果混为一谈。")
    if context.is_cloud:
        st.info("在线版支持数据检查和预生成结果查看；HEC-HMS、大批量事件和 LSTM 请在本地运行，EnKF 建议降为 10 个成员。")
    root = DEFAULT_OUTPUT
    readiness = assess_hindcast_readiness(DEMO_SOURCE)
    cols = st.columns(5)
    cols[0].metric("事件", readiness["event_count"])
    cols[1].metric("合格事件", readiness["qualified_event_count"])
    cols[2].metric("验证等级", readiness["validation_level"])
    cols[3].metric("降雨覆盖率", f"{readiness['rainfall_coverage']:.0%}")
    cols[4].metric("流量覆盖率", f"{readiness['streamflow_coverage']:.0%}")

    tabs = st.tabs(["数据就绪度", "事件目录", "观测质量", "站点映射", "事件划分", "多事件回放", "率定", "数据同化", "提前期验证", "模型表现", "报告与下载"])
    with tabs[0]:
        st.json(readiness)
        if st.button("检查 Demo 数据"):
            st.json(prepare_hindcast_workspace(DEMO_SOURCE, root))
    with tabs[1]: _show(root / "events/flood_event_catalog.xlsx")
    with tabs[2]: _show(root / "observations/observation_qc_summary.xlsx")
    with tabs[3]: _show(root / "mappings/station_model_mapping.xlsx")
    with tabs[4]:
        path = root / "splits/event_split.yaml"
        st.code(path.read_text(encoding="utf-8") if path.exists() else "尚未生成", language="yaml")
    with tabs[5]:
        if st.button("运行全部事件", disabled=context.is_cloud):
            st.json(run_hydrolite_hindcast_batch(context.project_dir))
        _show(root / "summary/event_metrics.xlsx")
    with tabs[6]: _show(root / "calibration/parameter_search_results.xlsx")
    with tabs[7]:
        if st.button("运行 Nudging 与 EnKF", disabled=context.is_cloud):
            st.json(run_assimilation_batch(context.project_dir, root / "assimilation"))
        _show(root / "assimilation/assimilation_metrics.xlsx")
    with tabs[8]:
        if st.button("运行提前期验证", disabled=context.is_cloud):
            st.json(run_lead_time_validation(root / "assimilation", root / "lead_time"))
        _show(root / "lead_time/lead_time_summary.xlsx")
    with tabs[9]:
        _show(root / "summary/model_validation_summary.xlsx")
        charts = root / "summary/charts"
        for chart in sorted(charts.glob("*.png")):
            st.image(str(chart), caption=chart.stem)
    with tabs[10]:
        if st.button("生成验证报告"): st.json(summarize_hindcast_validation(root))
        for name in ("model_validation_report_zh.md", "model_validation_report_en.md", "hindcast_validation_bundle.zip"):
            path = root / "summary" / name
            if path.exists():
                st.download_button(f"下载 {name}", path.read_bytes(), file_name=name)
