from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

from hydrolite.gee.export import write_hydrolite_gee_outputs
from hydrolite.gee.datasets import list_supported_datasets
from hydrolite.ui.components import (
    read_text_if_exists,
    run_command,
    show_download,
    show_json,
    show_markdown_file,
    safe_read_csv,
    safe_read_excel,
)
from hydrolite.ui.state import OUTPUT_ROOT, PROJECT_ROOT, WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("GEE 数据中心")
    st.caption("查看 GEE 状态，生成 demo basin 的 HydroLite 输入建议与数据产品。")
    init = context.gee_status.get("initialization", {}) if isinstance(context.gee_status, dict) else {}
    c1, c2, c3 = st.columns(3)
    c1.metric("GEE 状态", str(init.get("status", "")))
    c2.metric("GEE_PROJECT", context.gee_project or "not detected")
    c3.metric("auth_source", str(init.get("auth_source", "")))
    show_json(context.gee_status)
    if not context.gee_project_detected or init.get("status") != "available":
        st.warning("GEE 未就绪。请设置 `GEE_PROJECT`，必要时本地运行 `python scripts/gee_auth_local.py` 完成认证。")
        next_steps = init.get("next_steps") or []
        if next_steps:
            st.write(next_steps)

    st.subheader("支持数据集")
    st.write(", ".join(list_supported_datasets()))

    cols = st.columns(2)
    if cols[0].button("GEE 诊断", use_container_width=True):
        with st.spinner("正在运行 GEE 诊断..."):
            ok, output = run_command([sys.executable, "scripts/diagnose_gee.py"], timeout=180)
        (st.success if ok else st.error)(output or "GEE 诊断完成")
    if cols[1].button("生成 HydroLite 输入", use_container_width=True):
        with st.spinner("正在生成 GEE 到 HydroLite 输入..."):
            try:
                outputs = write_hydrolite_gee_outputs(PROJECT_ROOT / "configs" / "gee.example.yaml")
                st.success(f"已生成: `{outputs['gee_to_hydrolite_report_md'].parent}`")
            except Exception as exc:
                st.error(f"GEE 输入生成失败: {exc}")

    root = OUTPUT_ROOT / "gee" / "hydrolite_inputs"
    st.subheader("GEE 输出")
    for path, title in [
        (OUTPUT_ROOT / "gee" / "gee_summary.xlsx", "gee_summary.xlsx"),
        (root / "gee_basin_summary.xlsx", "gee_basin_summary.xlsx"),
        (root / "gee_parameter_suggestions.xlsx", "gee_parameter_suggestions.xlsx"),
    ]:
        if path.exists():
            st.write(title)
            st.dataframe(safe_read_excel(path), use_container_width=True)
            show_download(f"下载 {path.name}", path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for path in [root / "gee_chirps_rainfall.csv", root / "gee_temperature_daily.csv", root / "gee_basin_summary.csv"]:
        if path.exists():
            st.write(path.name)
            st.dataframe(safe_read_csv(path).head(200), use_container_width=True)
            show_download(f"下载 {path.name}", path, "text/csv")
    suggestion_yaml = root / "gee_parameter_suggestions.yaml"
    if suggestion_yaml.exists():
        st.code(read_text_if_exists(suggestion_yaml), language="yaml")
        show_download("下载 gee_parameter_suggestions.yaml", suggestion_yaml, "text/yaml")
    show_markdown_file("gee_to_hydrolite_report.md", root / "gee_to_hydrolite_report.md")
    show_download("下载 gee_to_hydrolite_report.md", root / "gee_to_hydrolite_report.md", "text/markdown")
