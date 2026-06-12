from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

from hydrolite.ui.components import read_text_if_exists, run_command, show_download, show_json
from hydrolite.ui.state import OUTPUT_ROOT, PROJECT_ROOT, WorkbenchContext, dependency_versions, get_git_commit


def render(context: WorkbenchContext) -> None:
    st.header("系统诊断")
    st.caption("查看运行环境、依赖、Git、GEE、SWMM、OpenHydroNet 和 Streamlit 诊断。")

    cols = st.columns(4)
    cols[0].metric("Python", sys.version.split()[0])
    cols[1].metric("Git commit", get_git_commit() or "unknown")
    cols[2].metric("Streamlit Cloud", str(context.is_cloud))
    cols[3].metric("cwd", str(Path.cwd()))

    st.subheader("关键依赖版本")
    st.dataframe(pd.DataFrame([dependency_versions()]), use_container_width=True)

    st.subheader("GEE 诊断")
    show_json(context.gee_status)
    st.subheader("OpenHydroNet 诊断")
    show_json(context.openhydronet_status)
    st.subheader("SWMM 诊断")
    for path in [
        OUTPUT_ROOT / "swmm_backend_diagnosis.txt",
        OUTPUT_ROOT / "swmm_solver_env_diagnosis.txt",
    ]:
        if path.exists():
            st.write(path.name)
            st.code(read_text_if_exists(path), language="text")

    cols = st.columns(3)
    if cols[0].button("运行 GEE 诊断", use_container_width=True):
        with st.spinner("正在运行 GEE 诊断..."):
            ok, output = run_command([sys.executable, "scripts/diagnose_gee.py"], timeout=180)
        (st.success if ok else st.error)(output or "GEE 诊断完成")
    if cols[1].button("运行 OpenHydroNet 诊断", use_container_width=True):
        with st.spinner("正在运行 OpenHydroNet 诊断..."):
            ok, output = run_command([sys.executable, "scripts/diagnose_openhydronet.py"], timeout=180)
        (st.success if ok else st.error)(output or "OpenHydroNet 诊断完成")
    if cols[2].button("运行 Streamlit 本地诊断", use_container_width=True):
        with st.spinner("正在运行 Streamlit 诊断..."):
            ok, output = run_command([sys.executable, "scripts/diagnose_streamlit_local.py"], timeout=180)
        (st.success if ok else st.error)(output or "Streamlit 诊断完成")

    st.subheader("诊断报告")
    for path in [
        OUTPUT_ROOT / "gee_diagnosis.txt",
        OUTPUT_ROOT / "openhydronet_diagnosis.txt",
        OUTPUT_ROOT / "streamlit_local_diagnosis.txt",
        OUTPUT_ROOT / "swmm_backend_diagnosis.txt",
        OUTPUT_ROOT / "swmm_solver_env_diagnosis.txt",
    ]:
        if path.exists():
            st.write(path.name)
            st.code(read_text_if_exists(path), language="text")
            show_download(f"下载 {path.name}", path, "text/plain")
