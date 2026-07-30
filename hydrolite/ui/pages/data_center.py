from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import streamlit as st

from hydrolite.connectors import list_connectors
from hydrolite.data_acquisition import create_acquisition_plan, write_acquisition_report
from hydrolite.data_center import write_data_center_reports
from hydrolite.data_quality_center import run_workspace_quality_checks, write_data_quality_report
from hydrolite.data_registry import list_dataset_types, write_data_registry_report
from hydrolite.data_requirements import build_project_data_requirement_matrix, write_data_readiness_report
from hydrolite.data_upload import copy_upload_to_workspace, inspect_uploaded_file, preview_uploaded_dataset
from hydrolite.input_builder import build_all_inputs
from hydrolite.data_lineage import validate_lineage_graph, write_lineage_report
from hydrolite.workspace import create_workspace, inspect_workspace, list_workspace_datasets
from hydrolite.ui.state import PROJECT_ROOT, WorkbenchContext


OUTPUT = PROJECT_ROOT / "output" / "data_center"


def _safe_workspace(value: str, context: WorkbenchContext) -> tuple[Path, bool]:
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    allowed = PROJECT_ROOT / ("output" if context.is_cloud else "workspaces")
    safe = allowed.resolve() in resolved.parents or resolved == allowed.resolve()
    return resolved, safe and "data_raw" not in resolved.parts


def render(context: WorkbenchContext) -> None:
    st.header("数据中心")
    st.caption("真实项目数据上传、识别、字段映射、质量校验、血缘、外部数据计划与模型输入准备。")
    st.warning("原始上传文件保持只读；只有通过质量检查的 standardized/derived 数据可进入模型输入。")
    workspace_value = st.text_input("工作区路径", value="output/demo_workspace" if context.is_cloud else "workspaces/real_project")
    project_name = st.text_input("项目名称", value="Real Project")
    workspace, safe = _safe_workspace(workspace_value, context)
    if not safe:
        st.error("工作区必须位于本地 workspaces/ 或云端 output/ 下，且不能位于 data_raw。")

    tabs = st.tabs(["项目", "上传", "字段映射", "数据质量", "GEE", "Earthdata", "Copernicus", "STAC", "数据需求", "模型输入", "血缘", "下载与报告"])
    with tabs[0]:
        if st.button("创建工作区", disabled=not safe):
            try:
                st.json(create_workspace(workspace, project_name))
            except FileExistsError:
                st.info("工作区已存在，未覆盖。")
        st.json(inspect_workspace(workspace))
    with tabs[1]:
        dataset_type = st.selectbox("声明的数据类型（可选）", ["自动识别"] + [row["dataset_type_id"] for row in list_dataset_types()])
        uploads = st.file_uploader("上传单个或多个文件", accept_multiple_files=True, help="支持 CSV/XLSX/GeoJSON/ZIP/ASCII Grid；大型栅格建议本地使用。")
        if uploads and workspace.exists():
            for upload in uploads:
                staging = workspace / "uploads" / Path(upload.name).name
                staging.parent.mkdir(parents=True, exist_ok=True)
                staging.write_bytes(upload.getbuffer())
                try:
                    record = copy_upload_to_workspace(staging, workspace)
                    if dataset_type != "自动识别":
                        manifest_path = workspace / "workspace_manifest.json"
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest["datasets"][-1]["user_declared_type"] = dataset_type
                        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
                    st.success(f"上传完成：{record['dataset_id']}")
                    st.json(inspect_uploaded_file(workspace / record["raw_path"]))
                    st.dataframe(pd.DataFrame(preview_uploaded_dataset(workspace / record["raw_path"])["preview"]).head(20), use_container_width=True)
                except Exception as exc:
                    st.error(f"{upload.name}: {exc}")
    with tabs[2]:
        rows = list_workspace_datasets(workspace) if workspace.exists() else []
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
        st.info("低置信度映射必须由用户确认；CLI 可运行 `hydrolite data mapping` 保存候选。")
    with tabs[3]:
        if st.button("运行工作区质量检查", disabled=not workspace.exists()):
            result = run_workspace_quality_checks(workspace)
            write_data_quality_report(OUTPUT, result)
            st.session_state["data_quality"] = result
        if "data_quality" in st.session_state:
            st.write(f"质量状态：`{st.session_state['data_quality']['status']}`")
            st.dataframe(st.session_state["data_quality"]["issues"], use_container_width=True)
    connector_rows = {row["connector_id"]: row for row in list_connectors()}
    for tab, connector_id in zip(tabs[4:8], ("gee", "earthdata", "cds", "stac")):
        with tab:
            st.json(connector_rows[connector_id])
            st.info("搜索必须提供 bbox 与时间范围；真实下载默认关闭，凭证不会显示。")
    with tabs[8]:
        workflow = st.selectbox("应用场景", ["full_modeling_workflow", "hydrolite_event_model", "flood_forecast", "rusle", "water_quality"])
        if st.button("生成数据需求", disabled=not workspace.exists()):
            matrix = build_project_data_requirement_matrix(workflow, workspace)
            write_data_readiness_report(OUTPUT, {"workflow_id": workflow, "matrix": matrix})
            st.dataframe(matrix, use_container_width=True)
    with tabs[9]:
        if st.button("构建模型输入", disabled=not workspace.exists()):
            st.json(build_all_inputs(workspace, OUTPUT))
    with tabs[10]:
        if st.button("检查数据血缘", disabled=not workspace.exists()):
            result = validate_lineage_graph(workspace)
            write_lineage_report(OUTPUT, result)
            st.json({key: value for key, value in result.items() if key != "records"})
    with tabs[11]:
        if st.button("生成获取计划", disabled=not workspace.exists()):
            plan = create_acquisition_plan(workspace, "full_modeling_workflow")
            write_acquisition_report(OUTPUT, plan)
            st.dataframe(pd.DataFrame(plan["steps"]), use_container_width=True)
        if st.button("生成数据中心报告与安全包", disabled=not workspace.exists()):
            st.json({key: str(value) for key, value in write_data_center_reports(OUTPUT, workspace).items()})
        for path in sorted((PROJECT_ROOT / "templates" / "data_upload").glob("*")):
            if path.is_file():
                st.download_button(f"下载模板：{path.name}", path.read_bytes(), file_name=path.name, key=f"tpl_{path.name}")
        for name in ("data_center_report_zh.md", "data_center_report_en.md", "data_center_bundle.zip"):
            path = OUTPUT / name
            if path.is_file():
                st.download_button(f"下载 {name}", path.read_bytes(), file_name=name)
