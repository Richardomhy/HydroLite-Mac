from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.qgis_bridge import build_qgis_diagnosis, write_qgis_diagnosis
from hydrolite.ui.components import read_text_if_exists, show_download, show_json
from hydrolite.ui.state import OUTPUT_ROOT, WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("QGIS Bridge")
    st.caption("QGIS / QGIS-LTR / qgis_process / PyQGIS 可行性诊断；本阶段不开发完整 QGIS 插件。")

    md_path = OUTPUT_ROOT / "qgis" / "qgis_diagnosis.md"
    json_path = OUTPUT_ROOT / "qgis" / "qgis_diagnosis.json"

    if st.button("运行 QGIS 诊断", use_container_width=True):
        with st.spinner("正在探测 QGIS 路径与 PyQGIS 环境..."):
            outputs = write_qgis_diagnosis()
        st.success(f"诊断已生成: `{outputs['md']}`")

    diagnosis = build_qgis_diagnosis()
    apps = diagnosis["qgis_apps"]
    version = diagnosis["qgis_process_version"]
    pyqgis = diagnosis["pyqgis_import"]
    recommendation = diagnosis["recommendation"]

    c1, c2, c3 = st.columns(3)
    c1.metric("QGIS.app", str(apps["qgis_app_exists"]))
    c2.metric("QGIS-LTR.app", str(apps["qgis_ltr_app_exists"]))
    c3.metric("推荐方式", recommendation["mode"])

    if diagnosis["status"] == "warning":
        st.warning("当前环境未检测到可用 QGIS Bridge，可先使用 HydroLite 独立工作流。")

    st.subheader("qgis_process 候选路径")
    st.dataframe(pd.DataFrame(diagnosis["qgis_process_candidates"]), use_container_width=True)
    st.write(f"qgis_process --version: `{version.get('stdout') or version.get('stderr') or 'unavailable'}`")

    st.subheader("PyQGIS")
    st.write(f"candidate python: `{pyqgis['python']}`")
    st.write(f"import qgis / PyQt5: `{pyqgis['minimal_check']}`")
    if pyqgis.get("stderr"):
        st.code(pyqgis["stderr"], language="text")

    st.subheader("推荐集成方式")
    st.info(f"{recommendation['mode']}: {recommendation['reason']}")

    st.subheader("诊断报告")
    if md_path.exists():
        st.markdown(read_text_if_exists(md_path))
        show_download("下载 qgis_diagnosis.md", md_path, "text/markdown")
    if json_path.exists():
        show_json(diagnosis)
        show_download("下载 qgis_diagnosis.json", json_path, "application/json")

    st.subheader("后续 QGIS Bridge 开发路线")
    st.markdown(
        """
- 先确认 `qgis_process` 或 PyQGIS 是否可用。
- 最小方案优先读写 HydroLite 数据模板和 GeoJSON/CSV。
- 暂不直接开发完整 QGIS 插件，也不依赖第三方 ChatGPT/QGIS 插件。
- 若 QGIS 不可用，HydroLite 项目、校验、运行、报告流程仍可独立使用。
"""
    )
