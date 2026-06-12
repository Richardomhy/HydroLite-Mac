from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.project import validate_project
from hydrolite.validate import validate_target
from hydrolite.ui.components import read_project_validation_outputs, read_validation_outputs, show_download, show_markdown_file
from hydrolite.ui.state import CASES_DIR, OUTPUT_ROOT, WorkbenchContext


def _status_counts(df: pd.DataFrame) -> tuple[int, int]:
    if df.empty:
        return 0, 0
    failed = int((df.get("validation_status", pd.Series(dtype=str)).astype(str) == "failed").sum())
    warning = int((df.get("validation_status", pd.Series(dtype=str)).astype(str) == "warning").sum())
    return failed, warning


def render(context: WorkbenchContext) -> None:
    st.header("数据与校验")
    st.caption("运行模型前检查 YAML、CSV、SWMM 配置和输出路径。")
    if not context.project_loaded:
        st.error(context.error_message)
        return

    st.subheader("项目 cases")
    st.write(context.cases or "暂无情景")

    cols = st.columns(2)
    if cols[0].button("校验当前项目", use_container_width=True):
        with st.spinner("正在校验项目 cases..."):
            result = validate_project(context.project_dir)
        st.success(f"项目校验完成: `{result['xlsx']}`")
    if cols[1].button("校验全部情景", use_container_width=True):
        with st.spinner("正在校验根目录 cases/..."):
            result = validate_target(CASES_DIR)
        if result.has_fatal_errors:
            st.error(f"根目录情景校验存在 fatal error: `{result.outputs.xlsx}`")
        else:
            st.success(f"根目录情景校验完成: `{result.outputs.xlsx}`")

    outputs = read_project_validation_outputs(context.project_dir)
    overview = outputs.get("case_overview")
    failed, warning = _status_counts(overview if isinstance(overview, pd.DataFrame) else pd.DataFrame())
    c1, c2 = st.columns(2)
    c1.metric("failed", failed)
    c2.metric("warning", warning)

    for key, title in [
        ("project_checks", "project_checks"),
        ("case_overview", "case_overview"),
        ("case_checks", "case_checks"),
        ("case_errors", "case_errors"),
        ("case_warnings", "case_warnings"),
    ]:
        df = outputs.get(key)
        if isinstance(df, pd.DataFrame):
            st.write(title)
            st.dataframe(df, use_container_width=True)

    show_markdown_file("project_validation_report.md", context.project_dir / "reports" / "project_validation_report.md")
    show_download(
        "下载 project_validation.xlsx",
        context.project_dir / "reports" / "project_validation.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    show_download("下载 project_validation_report.md", context.project_dir / "reports" / "project_validation_report.md", "text/markdown")

    root_validation = read_validation_outputs(OUTPUT_ROOT)
    if root_validation:
        st.subheader("根目录 validation_summary.xlsx")
        for key in ("overview", "checks"):
            df = root_validation.get(key)
            if isinstance(df, pd.DataFrame):
                st.dataframe(df, use_container_width=True)
