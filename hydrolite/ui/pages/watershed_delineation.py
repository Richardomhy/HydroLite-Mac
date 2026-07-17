from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.__version__ import __version__
from hydrolite.ui.components import read_text_if_exists, safe_read_excel, show_download, show_json
from hydrolite.ui.state import OUTPUT_ROOT, WorkbenchContext
from hydrolite.watershed import (
    create_demo_dem,
    detect_watershed_backends,
    inspect_dem,
    run_watershed_mvp,
    validate_watershed_outputs,
)


def render(context: WorkbenchContext) -> None:
    st.header("流域划分")
    st.caption(f"HydroLite Studio v{__version__}")
    st.warning("当前为流域划分 MVP，用于验证工作流和环境，不替代专业 GIS 人工复核。")

    output_dir = OUTPUT_ROOT / "watershed"
    demo_dem = output_dir / "demo_dem.asc"
    backends = detect_watershed_backends()
    c1, c2, c3 = st.columns(3)
    c1.metric("qgis_process", "available" if backends["qgis_process_available"] else "unavailable")
    c2.metric("后端状态", backends["status"])
    c3.metric("fallback", "available" if backends["fallback_available"] else "unavailable")
    st.caption(backends["message"])
    if backends.get("qgis_version"):
        st.code(backends["qgis_version"], language="text")

    candidates = pd.DataFrame(backends["algorithm_candidates"])
    if not candidates.empty:
        display = candidates.copy()
        display["matched_algorithms"] = display["matched_algorithms"].apply(lambda values: "; ".join(values))
        st.subheader("流域划分后端探测")
        st.dataframe(display, use_container_width=True)

    cols = st.columns(4)
    if cols[0].button("创建 demo DEM", use_container_width=True):
        path = create_demo_dem(demo_dem)
        st.success(f"DEM 已生成: `{path}`")
    if cols[1].button("DEM 检查", use_container_width=True):
        if not demo_dem.exists():
            create_demo_dem(demo_dem)
        show_json(inspect_dem(demo_dem))
    if cols[2].button("运行 Watershed MVP", use_container_width=True):
        with st.spinner("正在运行小型 DEM 工作流..."):
            result = run_watershed_mvp(output_dir=output_dir)
        st.success(f"MVP 完成，状态: `{result['status']}`")
        show_json(result)
    if cols[3].button("校验输出", use_container_width=True):
        show_json(validate_watershed_outputs(output_dir))

    report = output_dir / "watershed_report.md"
    diagnosis = output_dir / "watershed_diagnosis.json"
    backend_summary = output_dir / "watershed_backend_summary.xlsx"
    st.subheader("诊断报告")
    text = read_text_if_exists(report)
    if text:
        st.markdown(text)
    else:
        st.info("尚未生成 watershed_report.md。")

    summary = safe_read_excel(backend_summary, "backend_summary")
    if not summary.empty:
        st.subheader("Backend summary")
        st.dataframe(summary, use_container_width=True)

    st.subheader("输出文件")
    files = [path for path in sorted(output_dir.glob("*")) if path.is_file()] if output_dir.exists() else []
    if files:
        st.dataframe(pd.DataFrame({"file": [str(path) for path in files], "size_bytes": [path.stat().st_size for path in files]}), use_container_width=True)
    else:
        st.info("尚无输出文件。")

    downloads = [
        ("下载 watershed_report.md", report, "text/markdown"),
        ("下载 watershed_diagnosis.json", diagnosis, "application/json"),
        ("下载 basin_boundary.geojson", output_dir / "basin_boundary.geojson", "application/geo+json"),
        ("下载 stream_network.geojson", output_dir / "stream_network.geojson", "application/geo+json"),
        ("下载 subbasins.geojson", output_dir / "subbasins.geojson", "application/geo+json"),
        ("下载 hydrolite_subbasins.csv", output_dir / "hydrolite_subbasins.csv", "text/csv"),
        ("下载 hydrolite_reaches.csv", output_dir / "hydrolite_reaches.csv", "text/csv"),
    ]
    for label, path, mime in downloads:
        show_download(label, path, mime)

    st.subheader("后续路线")
    st.markdown(
        """
- 将真实 DEM 在 QGIS 中统一投影、分辨率与 NoData。
- 补齐稳定的 GRASS/SAGA/WhiteboxTools 汇流累积和出口点流域划分链。
- 在 QGIS 中人工复核河网阈值、出口点吸附、分水岭和子流域面积。
- 复核后将 CSV/GeoJSON 交给 `QGIS Bridge` 或 `项目向导`。
"""
    )

