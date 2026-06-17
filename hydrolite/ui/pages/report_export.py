from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.export_report import (
    export_project_report_bundle,
    list_report_assets,
    render_project_report_all,
    render_project_report_docx,
    render_project_report_html,
    render_project_report_markdown,
    render_project_report_pdf,
)
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

    st.subheader("一键交付报告")
    report_cols = st.columns(3)
    if report_cols[0].button("生成 Markdown", use_container_width=True):
        with st.spinner("正在生成 Markdown 报告..."):
            path = render_project_report_markdown(context.project_dir)
        st.success(f"Markdown 报告已生成: `{path}`")
    if report_cols[1].button("生成 Word", use_container_width=True):
        with st.spinner("正在生成 Word 报告..."):
            path = render_project_report_docx(context.project_dir)
        st.success(f"Word 报告已生成: `{path}`")
    if report_cols[2].button("生成 HTML", use_container_width=True):
        with st.spinner("正在生成 HTML 报告..."):
            path = render_project_report_html(context.project_dir)
        st.success(f"HTML 报告已生成: `{path}`")

    pdf_cols = st.columns(3)
    if pdf_cols[0].button("生成 PDF", use_container_width=True):
        with st.spinner("正在生成 PDF 或 fallback 说明..."):
            path = render_project_report_pdf(context.project_dir)
        st.success(f"PDF 输出已生成: `{path}`")
    if pdf_cols[1].button("生成报告包", use_container_width=True):
        with st.spinner("正在生成报告包..."):
            path = export_project_report_bundle(context.project_dir)
        st.success(f"报告包已生成: `{path}`")
    if pdf_cols[2].button("一键生成全部", use_container_width=True):
        with st.spinner("正在生成全部报告资产..."):
            outputs = render_project_report_all(context.project_dir)
        st.success("报告资产已生成。")
        st.json({key: str(value) for key, value in outputs.items()})

    show_markdown_file("hydrolite_report.md", context.project_dir / "output" / "comparison" / "hydrolite_report.md")
    show_markdown_file("project_summary.md", context.project_dir / "project_summary.md")
    show_markdown_file("project_report.md", context.project_dir / "reports" / "project_report.md")

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

    st.subheader("报告资产")
    report_assets = list_report_assets(context.project_dir)
    if report_assets:
        st.dataframe(
            pd.DataFrame(
                [
                    {"file": str(path.relative_to(context.project_dir)), "size_bytes": path.stat().st_size}
                    for path in report_assets
                ]
            ),
            use_container_width=True,
        )
    else:
        st.info("暂无报告资产。")

    show_download(
        "下载 hydrolite_report.md",
        context.project_dir / "output" / "comparison" / "hydrolite_report.md",
        "text/markdown",
    )
    show_download("下载 project_summary.md", context.project_dir / "project_summary.md", "text/markdown")
    show_download("下载 project_report.md", context.project_dir / "reports" / "project_report.md", "text/markdown")
    show_download(
        "下载 project_report.docx",
        context.project_dir / "reports" / "project_report.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    show_download("下载 project_report.html", context.project_dir / "reports" / "project_report.html", "text/html")
    show_download("下载 project_report.pdf", context.project_dir / "reports" / "project_report.pdf", "application/pdf")
    show_download(
        "下载 PDF unavailable 说明",
        context.project_dir / "reports" / "project_report_pdf_unavailable.md",
        "text/markdown",
    )
    show_download(
        "下载 project_report_bundle.zip",
        context.project_dir / "reports" / "project_report_bundle.zip",
        "application/zip",
    )
    show_download(
        "下载项目包 zip",
        context.project_dir / "reports" / f"{context.project_id}_package.zip",
        "application/zip",
    )
