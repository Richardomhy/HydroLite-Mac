from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.project import run_project_batch, run_project_case
from hydrolite.ui.components import (
    output_dir_for_case,
    read_result_flow,
    read_summary,
    read_water_balance,
    show_download,
    show_dataframe,
    show_markdown_file,
)
from hydrolite.ui.state import WorkbenchContext


def _show_case_outputs(output_dir: Path) -> None:
    flow = output_dir / "result_flow.csv"
    summary = output_dir / "summary.xlsx"
    balance = output_dir / "water_balance.xlsx"
    hydrograph = output_dir / "hydrograph.png"
    if hydrograph.exists():
        st.image(str(hydrograph), caption="hydrograph.png")
    if flow.exists():
        df = read_result_flow(flow)
        show_dataframe("result_flow.csv", df)
        if "outflow_cms" in df.columns:
            st.line_chart(df.set_index(df.columns[0])["outflow_cms"])
        show_download("下载 result_flow.csv", flow, "text/csv")
    if summary.exists():
        show_dataframe("summary.xlsx", read_summary(summary))
        show_download("下载 summary.xlsx", summary, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if balance.exists():
        subbasin, outlet = read_water_balance(balance)
        show_dataframe("water_balance subbasin_balance", subbasin)
        show_dataframe("water_balance outlet_balance", outlet)
        show_download("下载 water_balance.xlsx", balance, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def render(context: WorkbenchContext) -> None:
    st.header("情景运行")
    st.caption("选择项目情景，运行单情景或项目批量情景。")
    if not context.project_loaded:
        st.error(context.error_message)
        return
    if not context.cases:
        st.warning("当前项目没有 YAML 情景。")
        return

    selected = st.selectbox("项目情景", context.cases)
    case_file = context.project_dir / "cases" / selected
    show_markdown_file("情景 YAML", case_file)

    cols = st.columns(3)
    if cols[0].button("运行选中情景", use_container_width=True):
        with st.spinner(f"正在运行 {selected}..."):
            outputs = run_project_case(context.project_dir, selected)
        st.success(f"运行完成: `{outputs.output_dir}`")
    if cols[1].button("批量运行项目情景", use_container_width=True):
        with st.spinner("正在批量运行项目情景..."):
            summary, rows, failed = run_project_batch(context.project_dir)
        if failed:
            st.warning(f"批量运行完成但存在失败: {len(failed)}；汇总 `{summary}`")
        else:
            st.success(f"批量运行完成: {len(rows)} 个情景；汇总 `{summary}`")
    cols[2].info(f"输出目录: `{output_dir_for_case(context.project_dir, Path(selected).stem)}`")

    output_dir = output_dir_for_case(context.project_dir, Path(selected).stem)
    _show_case_outputs(output_dir)

    log_file = output_dir / "run.log"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8").splitlines()[-80:]
        st.subheader("运行日志摘要")
        st.code("\n".join(lines), language="text")

    batch = context.project_dir / "output" / "batch_summary.xlsx"
    if batch.exists():
        show_dataframe("batch_summary.xlsx", pd.read_excel(batch))
        show_download("下载 batch_summary.xlsx", batch, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
