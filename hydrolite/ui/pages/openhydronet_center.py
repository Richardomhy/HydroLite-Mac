from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

from hydrolite.openhydronet.runner import run_openhydronet_prepare_inputs, run_openhydronet_smoke
from hydrolite.ui.components import (
    read_openhydronet_temperature_stats,
    run_command,
    show_download,
    show_json,
    show_markdown_file,
    safe_read_csv,
    safe_read_excel,
)
from hydrolite.ui.state import OUTPUT_ROOT, PROJECT_ROOT, WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("OpenHydroNet AI 输入")
    st.caption("准备 OpenHydroNet-ready 输入包；不训练模型，不运行真实大规模推理。")
    st.warning("当前为 OpenHydroNet-ready input package，不代表已经完成真实 AI 模型预测。")
    env = context.openhydronet_status
    cols = st.columns(4)
    cols[0].metric("环境状态", str(env.get("status", "")))
    cols[1].metric("accelerator", str(env.get("accelerator", "CPU")))
    cols[2].metric("torch", "yes" if env.get("torch_installed") else "no")
    cols[3].metric("repo", "yes" if env.get("repo_exists") else "no")
    show_json(env)

    config = PROJECT_ROOT / "configs" / "openhydronet.example.yaml"
    cols = st.columns(3)
    if cols[0].button("运行 OpenHydroNet 诊断", use_container_width=True):
        with st.spinner("正在运行 OpenHydroNet 诊断..."):
            ok, output = run_command([sys.executable, "scripts/diagnose_openhydronet.py"], timeout=180)
        (st.success if ok else st.error)(output or "OpenHydroNet 诊断完成")
    if cols[1].button("运行 smoke test", use_container_width=True):
        with st.spinner("正在运行 smoke test..."):
            result = run_openhydronet_smoke(config)
        st.success(f"smoke status: `{result['status']}`")
    if cols[2].button("生成 AI 输入包", use_container_width=True):
        with st.spinner("正在生成 OpenHydroNet 输入包..."):
            result = run_openhydronet_prepare_inputs(config)
        st.success(f"输入包状态: `{result['status']}`；目录 `{result['output_dir']}`")

    inputs = OUTPUT_ROOT / "openhydronet" / "inputs"
    for path in [
        inputs / "static_attributes.csv",
        inputs / "meteorological_forcing.csv",
        inputs / "observed_streamflow.csv",
        inputs / "hydrolite_streamflow.csv",
    ]:
        if path.exists():
            st.write(path.name)
            df = safe_read_csv(path)
            st.dataframe(df.head(200), use_container_width=True)
            if path.name == "meteorological_forcing.csv":
                stats = read_openhydronet_temperature_stats(path)
                st.write(f"temperature_mean_c 状态: `{stats}`")
            show_download(f"下载 {path.name}", path, "text/csv")
    quality = inputs / "input_quality_report.xlsx"
    if quality.exists():
        st.write("input_quality_report.xlsx")
        for sheet in ("overview", "warnings", "observed_streamflow_checks"):
            df = safe_read_excel(quality, sheet)
            if not df.empty:
                st.dataframe(df, use_container_width=True)
        show_download("下载 input_quality_report.xlsx", quality, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    show_markdown_file("openhydronet_input_report.md", inputs / "openhydronet_input_report.md")
    show_download("下载 openhydronet_input_report.md", inputs / "openhydronet_input_report.md", "text/markdown")
