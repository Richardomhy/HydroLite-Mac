from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.qgis_bridge import (
    DEMO_GIS_DIR,
    build_qgis_diagnosis,
    convert_qgis_layers_to_hydrolite_inputs,
    create_project_from_qgis_outputs,
    infer_hydrolite_field_mapping,
    qgis_bridge_demo,
    qgis_export_attributes_csv,
    qgis_export_vector,
    qgis_layer_info,
    qgis_process_algorithms,
    qgis_process_version,
    qgis_validate_vector_layer,
    run_qgis_project_workflow,
    validate_qgis_to_hydrolite_outputs,
    write_qgis_diagnosis,
)
from hydrolite.ui.components import read_text_if_exists, show_download, show_json
from hydrolite.ui.state import OUTPUT_ROOT, WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("QGIS Bridge")
    st.caption("qgis_process 自动化桥接 MVP；本阶段不是完整 QGIS 插件，不使用 PyQGIS import。")

    md_path = OUTPUT_ROOT / "qgis" / "qgis_diagnosis.md"
    json_path = OUTPUT_ROOT / "qgis" / "qgis_diagnosis.json"
    demo_dir = OUTPUT_ROOT / "qgis_bridge_demo"
    demo_report = demo_dir / "qgis_bridge_demo_report.md"
    demo_summary = demo_dir / "qgis_bridge_demo_summary.json"
    demo_geojson = demo_dir / "demo_subbasins_export.geojson"
    demo_csv = demo_dir / "demo_subbasins_attributes.csv"
    demo_layer = DEMO_GIS_DIR / "demo_subbasins.geojson"

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

    st.subheader("qgis_process MVP")
    cols = st.columns(4)
    if cols[0].button("版本检查", use_container_width=True):
        st.code(qgis_process_version().get("stdout") or "qgis_process unavailable", language="text")
    if cols[1].button("算法列表预览", use_container_width=True):
        algorithms = qgis_process_algorithms()["algorithms"][:50]
        st.code("\n".join(algorithms) or "No algorithms returned", language="text")
    if cols[2].button("读取示例图层", use_container_width=True):
        show_json(qgis_layer_info(demo_layer))
    if cols[3].button("校验示例图层", use_container_width=True):
        show_json(qgis_validate_vector_layer(demo_layer))

    export_cols = st.columns(3)
    if export_cols[0].button("导出示例 GeoJSON", use_container_width=True):
        show_json(qgis_export_vector(demo_layer, demo_geojson))
    if export_cols[1].button("导出属性 CSV", use_container_width=True):
        show_json(qgis_export_attributes_csv(demo_layer, demo_csv))
    if export_cols[2].button("运行桥接 Demo", use_container_width=True):
        summary = qgis_bridge_demo()
        st.success(f"Demo 已生成: `{summary['outputs']['report']}`")

    show_download("下载 qgis_bridge_demo_report.md", demo_report, "text/markdown")
    show_download("下载 demo_subbasins_export.geojson", demo_geojson, "application/geo+json")
    show_download("下载 demo_subbasins_attributes.csv", demo_csv, "text/csv")

    st.subheader("QGIS 图层转 HydroLite 输入")
    st.caption("当前转换基于 GeoJSON 属性字段；面积/长度建议先在 QGIS 中计算好。HydroLite 不在此阶段做复杂投影面积计算。")
    subbasins_layer = st.text_input("subbasins GeoJSON", value=str(DEMO_GIS_DIR / "demo_subbasins.geojson"))
    reaches_layer = st.text_input("reaches GeoJSON", value=str(DEMO_GIS_DIR / "demo_reaches.geojson"))
    basin_layer = st.text_input("basin boundary GeoJSON", value=str(DEMO_GIS_DIR / "demo_basin_boundary.geojson"))
    conversion_dir = st.text_input("输出目录", value=str(OUTPUT_ROOT / "qgis_to_hydrolite"))

    conv_cols = st.columns(3)
    if conv_cols[0].button("推断字段映射", use_container_width=True):
        show_json(
            {
                "subbasins": infer_hydrolite_field_mapping(subbasins_layer, "subbasins"),
                "reaches": infer_hydrolite_field_mapping(reaches_layer, "reaches"),
            }
        )
    if conv_cols[1].button("转换为 HydroLite 输入", use_container_width=True):
        result = convert_qgis_layers_to_hydrolite_inputs(subbasins_layer, reaches_layer, basin_layer, conversion_dir)
        show_json(result)
    if conv_cols[2].button("校验转换结果", use_container_width=True):
        show_json(validate_qgis_to_hydrolite_outputs(conversion_dir))

    converted = Path(conversion_dir)
    st.write("转换后建议进入 `数据模板` 或 `项目向导` 页面继续校验和建项目。")
    for label, path, mime in [
        ("下载 subbasins.csv", converted / "subbasins.csv", "text/csv"),
        ("下载 reaches.csv", converted / "reaches.csv", "text/csv"),
        ("下载 basin_boundary.geojson", converted / "basin_boundary.geojson", "application/geo+json"),
        ("下载 mapping report", converted / "qgis_to_hydrolite_mapping_report.md", "text/markdown"),
        ("下载 manifest", converted / "qgis_to_hydrolite_manifest.json", "application/json"),
    ]:
        show_download(label, path, mime)

    st.subheader("从 QGIS 转换结果创建 HydroLite 项目")
    project_dir = st.text_input("项目目录", value="projects/qgis_demo_project")
    project_rainfall = st.text_input("rainfall_csv（可选）", value="")
    project_name = st.text_input("项目名称（可选）", value="QGIS Demo Project")
    project_cols = st.columns(2)
    project_result = None
    if project_cols[0].button("创建项目", use_container_width=True):
        try:
            project_result = create_project_from_qgis_outputs(
                conversion_dir,
                project_dir,
                rainfall_csv=project_rainfall or None,
                project_name=project_name or None,
            )
            st.success(f"项目已创建: `{project_result['project_dir']}`")
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
    if project_cols[1].button("运行完整工作流", use_container_width=True):
        try:
            project_result = run_qgis_project_workflow(
                conversion_dir,
                project_dir,
                rainfall_csv=project_rainfall or None,
                run_batch=True,
                run_compare=True,
                run_report=True,
            )
            st.success(f"工作流完成: `{project_result['project_dir']}`")
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
    if project_result:
        show_json(project_result)
    project_path = Path(project_dir)
    st.write("下一步：进入 `项目首页` 或 `报告与导出` 页面查看项目成果。")
    st.code(read_text_if_exists(project_path / "project.yaml"), language="yaml")
    st.markdown(read_text_if_exists(project_path / "reports" / "qgis_project_summary.md"))
    show_download("下载 qgis_project_summary.md", project_path / "reports" / "qgis_project_summary.md", "text/markdown")

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
- 当前 MVP 优先使用 `qgis_process`，并用 Python 标准库处理小型 GeoJSON/CSV 示例。
- 暂不直接开发完整 QGIS 插件，也不依赖第三方 ChatGPT/QGIS 插件。
- 若 QGIS 不可用，HydroLite 项目、校验、运行、报告流程仍可独立使用。
"""
    )
