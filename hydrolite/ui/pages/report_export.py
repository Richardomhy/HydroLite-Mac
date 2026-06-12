from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.project import compare_project_outputs, export_project_package, write_project_summary
from hydrolite.ui.components import recent_files, show_download, show_markdown_file
from hydrolite.ui.state import WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("报告与导出")
    st.caption("汇总报告、项目摘要、输出文件清单和项目包导出。")
    if not context.project_loaded:
        st.error(context.error_message)
        return

    cols = st.columns(2)
    if cols[0].button("生成项目报告", use_container_width=True):
        with st.spinner("正在刷新项目摘要与情景对比报告..."):
            write_project_summary(context.project_dir)
            compare_project_outputs(context.project_dir)
        st.success("项目报告已刷新。")
    if cols[1].button("导出项目包", use_container_width=True):
        with st.spinner("正在导出项目包..."):
            package = export_project_package(context.project_dir)
        st.success(f"项目包已生成: `{package}`")

    show_markdown_file("hydrolite_report.md", context.project_dir / "output" / "comparison" / "hydrolite_report.md")
    show_markdown_file("project_summary.md", context.project_dir / "project_summary.md")

    st.subheader("输出文件清单")
    files = recent_files(context.project_dir, limit=200)
    if files:
        st.dataframe(
            pd.DataFrame(
                [{"file": str(path.relative_to(context.project_dir)), "size_bytes": path.stat().st_size} for path in files]
            ),
            use_container_width=True,
        )
    else:
        st.info("暂无输出文件。")

    show_download(
        "下载 hydrolite_report.md",
        context.project_dir / "output" / "comparison" / "hydrolite_report.md",
        "text/markdown",
    )
    show_download("下载 project_summary.md", context.project_dir / "project_summary.md", "text/markdown")
    show_download(
        "下载项目包 zip",
        context.project_dir / "reports" / f"{context.project_id}_package.zip",
        "application/zip",
    )
