from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.project import validate_project
from hydrolite.ui.components import read_project_validation_outputs, show_markdown_file
from hydrolite.ui.state import PROJECT_ROOT, WorkbenchContext
from hydrolite.wizard import create_project_from_wizard, preview_wizard, validate_wizard_config, write_wizard_summary


TEMPLATE_OPTIONS = {
    "basic": "templates/wizard/basic_project.yaml",
    "hydrolite_only": "templates/wizard/hydrolite_only.yaml",
    "hydrolite_gee": "templates/wizard/hydrolite_gee.yaml",
    "hydrolite_swmm": "templates/wizard/hydrolite_swmm.yaml",
    "full_demo": "templates/wizard/full_demo.yaml",
}


def _wizard_config_from_form(
    project_name: str,
    project_path: str,
    modules: dict[str, bool],
    paths: dict[str, str],
) -> dict:
    project_dir = Path(project_path).expanduser()
    return {
        "project": {
            "name": project_name,
            "id": project_dir.name or "wizard_project",
            "description": "Project generated from HydroLite Studio project wizard.",
            "author": "HydroLite Studio",
        },
        "modules": modules,
        "case": {"name": project_dir.name or "wizard_case", "time_step_hours": 1.0},
        "data": {
            "mode": "reference",
            "rainfall_csv": paths["rainfall_csv"],
            "subbasin_csv": paths["subbasin_csv"],
            "reach_csv": paths["reach_csv"],
            "observed_streamflow_csv": paths["observed_streamflow_csv"],
            "swmm_inp": paths["swmm_inp"],
            "basin_boundary": paths["basin_boundary"],
        },
    }


def _safe_project_path(path: str, context: WorkbenchContext) -> tuple[bool, str]:
    project_path = Path(path).expanduser()
    resolved = project_path if project_path.is_absolute() else (PROJECT_ROOT / project_path).resolve()
    try:
        resolved.relative_to((PROJECT_ROOT / "projects").resolve())
    except ValueError:
        if context.is_cloud:
            return False, "Streamlit Cloud 环境下仅允许在 projects/ 下创建演示项目。"
    if "data_raw" in resolved.parts:
        return False, "项目路径不能位于 data_raw 下。"
    return True, ""


def render(context: WorkbenchContext) -> None:
    st.header("项目向导")
    st.caption("按步骤创建项目、选择数据、生成情景 YAML，并自动运行项目校验。")
    st.info("项目向导不新增模型算法；仅生成 project.yaml、case YAML 和项目摘要。")

    template_name = st.selectbox("模板选择", list(TEMPLATE_OPTIONS.keys()))
    template_path = TEMPLATE_OPTIONS[template_name]
    st.write(f"模板文件: `{template_path}`")

    default_project = f"projects/{template_name}_project"
    project_name = st.text_input("项目名称", value=f"{template_name.replace('_', ' ').title()} Project")
    project_path = st.text_input("项目路径", value=default_project)

    st.subheader("模块")
    c1, c2, c3, c4 = st.columns(4)
    modules = {
        "hydrolite": c1.checkbox("HydroLite", value=True),
        "swmm": c2.checkbox("SWMM", value=template_name in {"hydrolite_swmm", "full_demo"}),
        "gee": c3.checkbox("GEE", value=template_name in {"hydrolite_gee", "full_demo"}),
        "openhydronet": c4.checkbox("OpenHydroNet", value=template_name == "full_demo"),
    }

    st.subheader("数据路径")
    paths = {
        "rainfall_csv": st.text_input("rainfall_csv", value="data_demo/rainfall.csv"),
        "subbasin_csv": st.text_input("subbasin_csv", value="data_demo/subcatchments.csv"),
        "reach_csv": st.text_input("reach_csv", value="data_demo/reaches.csv"),
        "observed_streamflow_csv": st.text_input("observed_streamflow_csv", value="data_demo/observed/demo_observed_streamflow.csv"),
        "swmm_inp": st.text_input("swmm_inp", value="data_raw/swmm/demo.inp" if modules["swmm"] else ""),
        "basin_boundary": st.text_input("basin_boundary", value="data_demo/gee/demo_basin.geojson" if modules["gee"] else ""),
    }

    config = _wizard_config_from_form(project_name, project_path, modules, paths)
    safe, message = _safe_project_path(project_path, context)
    if not safe:
        st.error(message)

    cols = st.columns(3)
    if cols[0].button("预览项目", use_container_width=True):
        result = preview_wizard(config)
        st.json(result)
    if cols[1].button("创建项目", use_container_width=True, disabled=not safe):
        try:
            with st.spinner("正在创建项目并运行校验..."):
                result = create_project_from_wizard(config, project_path)
            st.success(f"项目已创建: `{result['project_dir']}`")
            st.json({key: str(value) for key, value in result.items()})
        except Exception as exc:
            st.error(f"创建项目失败: {exc}")
    if cols[2].button("校验项目", use_container_width=True, disabled=not Path(project_path).exists()):
        try:
            with st.spinner("正在校验项目..."):
                result = validate_project(project_path)
                write_wizard_summary(project_path)
            st.success(f"项目校验完成: `{result['xlsx']}`")
        except Exception as exc:
            st.error(f"项目校验失败: {exc}")

    validation = validate_wizard_config(config)
    st.subheader("向导配置检查")
    st.json(validation)

    wizard_summary = Path(project_path) / "reports" / "wizard_summary.md"
    show_markdown_file("wizard_summary.md", wizard_summary)
    outputs = read_project_validation_outputs(project_path)
    overview = outputs.get("case_overview")
    if isinstance(overview, pd.DataFrame):
        st.subheader("validation overview")
        st.dataframe(overview, use_container_width=True)
