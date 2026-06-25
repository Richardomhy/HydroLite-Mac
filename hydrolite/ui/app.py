from __future__ import annotations

from pathlib import Path

import streamlit as st

from hydrolite.__version__ import __version__
from hydrolite.ui.components import (
    read_comparison_outputs as _read_comparison_outputs,
    read_openhydronet_temperature_stats,
    read_project_validation_outputs,
    read_result_flow,
    read_summary,
    read_swmm_outputs,
    read_text_if_exists,
    read_validation_outputs,
    read_water_balance,
)
from hydrolite.ui.pages import (
    beta_feedback,
    comparison,
    data_templates,
    data_validation,
    diagnostics,
    gee_center,
    openhydronet_center,
    project_home,
    project_wizard,
    qgis_bridge,
    report_export,
    scenario_run,
    swmm_center,
    tutorial_demo,
)
from hydrolite.ui.state import (
    CASES_DIR,
    DEFAULT_PROJECT,
    OUTPUT_ROOT,
    PROJECT_ROOT,
    WorkbenchContext,
    is_streamlit_cloud,
    load_workbench_context,
    scan_case_files,
    scan_project_dirs,
    swmm_python_status,
)
from hydrolite.gee.auth import get_gee_status
from hydrolite.gee.basin import get_boundary_bbox
from hydrolite.gee.datasets import list_supported_datasets
from hydrolite.openhydronet.runner import detect_openhydronet_environment


PAGES = {
    "项目首页": project_home.render,
    "教程与 Demo": tutorial_demo.render,
    "Beta 反馈": beta_feedback.render,
    "数据模板": data_templates.render,
    "项目向导": project_wizard.render,
    "数据与校验": data_validation.render,
    "情景运行": scenario_run.render,
    "GEE 数据中心": gee_center.render,
    "QGIS Bridge": qgis_bridge.render,
    "SWMM 联动": swmm_center.render,
    "OpenHydroNet AI 输入": openhydronet_center.render,
    "结果对比": comparison.render,
    "报告与导出": report_export.render,
    "系统诊断": diagnostics.render,
}


def read_comparison_outputs(output_root: str | Path = OUTPUT_ROOT) -> dict:
    return _read_comparison_outputs(output_root)


def load_existing_outputs(output_dir: str | Path) -> dict[str, Path]:
    root = Path(output_dir)
    names = {
        "result_flow": "result_flow.csv",
        "summary": "summary.xlsx",
        "hydrograph": "hydrograph.png",
        "water_balance": "water_balance.xlsx",
        "swmm_summary": "swmm/swmm_summary.xlsx",
        "swmm_kpis": "swmm/swmm_kpis.xlsx",
        "swmm_node_depth": "swmm/node_depth_timeseries.csv",
        "swmm_link_flow": "swmm/link_flow_timeseries.csv",
        "swmm_system": "swmm/system_timeseries.csv",
        "swmm_coupling": "swmm/coupling_summary.xlsx",
        "observed_vs_simulated": "observed_vs_simulated.csv",
        "observed_vs_simulated_png": "observed_vs_simulated.png",
        "model_performance": "model_performance.xlsx",
        "model_performance_report": "model_performance_report.md",
    }
    return {key: root / name for key, name in names.items() if (root / name).exists()}


def get_gee_panel_payload() -> dict[str, object]:
    demo_boundary = PROJECT_ROOT / "data_demo" / "gee" / "demo_basin.geojson"
    return {
        "status": get_gee_status(),
        "datasets": list_supported_datasets(),
        "config_text": read_text_if_exists(PROJECT_ROOT / "configs" / "gee.example.yaml"),
        "diagnosis_text": read_text_if_exists(OUTPUT_ROOT / "gee_diagnosis.txt"),
        "demo_basin_bbox": get_boundary_bbox(demo_boundary),
        "outputs": {
            "gee_summary_xlsx": OUTPUT_ROOT / "gee" / "gee_summary.xlsx",
            "gee_basin_summary_xlsx": OUTPUT_ROOT / "gee" / "hydrolite_inputs" / "gee_basin_summary.xlsx",
            "gee_chirps_rainfall_csv": OUTPUT_ROOT / "gee" / "hydrolite_inputs" / "gee_chirps_rainfall.csv",
            "gee_temperature_daily_csv": OUTPUT_ROOT / "gee" / "hydrolite_inputs" / "gee_temperature_daily.csv",
            "gee_parameter_suggestions_xlsx": OUTPUT_ROOT / "gee" / "hydrolite_inputs" / "gee_parameter_suggestions.xlsx",
            "gee_to_hydrolite_report_md": OUTPUT_ROOT / "gee" / "hydrolite_inputs" / "gee_to_hydrolite_report.md",
        },
    }


def get_openhydronet_panel_payload() -> dict[str, object]:
    inputs = OUTPUT_ROOT / "openhydronet" / "inputs"
    return {
        "environment": detect_openhydronet_environment(),
        "config_text": read_text_if_exists(PROJECT_ROOT / "configs" / "openhydronet.example.yaml"),
        "diagnosis_text": read_text_if_exists(OUTPUT_ROOT / "openhydronet_diagnosis.txt"),
        "smoke_summary": OUTPUT_ROOT / "openhydronet" / "smoke_test_summary.xlsx",
        "smoke_report": OUTPUT_ROOT / "openhydronet" / "smoke_test_report.md",
        "input_package": {
            "static_attributes": inputs / "static_attributes.csv",
            "meteorological_forcing": inputs / "meteorological_forcing.csv",
            "hydrolite_streamflow": inputs / "hydrolite_streamflow.csv",
            "observed_streamflow": inputs / "observed_streamflow.csv",
            "basin_metadata": inputs / "basin_metadata.json",
            "input_manifest": inputs / "input_manifest.json",
            "input_quality_report": inputs / "input_quality_report.xlsx",
            "openhydronet_input_report": inputs / "openhydronet_input_report.md",
        },
        "stage": "environment diagnosis / smoke test only",
    }


def _sidebar_project_selector() -> Path:
    st.sidebar.title(f"HydroLite Studio v{__version__}")
    project_dirs = scan_project_dirs()
    default = DEFAULT_PROJECT if DEFAULT_PROJECT.exists() else (project_dirs[0] if project_dirs else DEFAULT_PROJECT)
    selected = st.sidebar.text_input("当前项目路径", value=str(default))
    return Path(selected).expanduser()


def _sidebar_status(context: WorkbenchContext) -> None:
    st.sidebar.caption("项目状态")
    st.sidebar.write(f"当前项目名称: `{context.project_name or 'unloaded'}`")
    gee_init = context.gee_status.get("initialization", {}) if isinstance(context.gee_status, dict) else {}
    st.sidebar.write(f"GEE 状态: `{gee_init.get('status', 'unknown')}`")
    st.sidebar.write(f"SWMM 状态: `{'external solver detected' if context.swmm_python_detected else 'current env/fallback'}`")
    st.sidebar.write(f"OpenHydroNet 状态: `{context.openhydronet_status.get('status', 'unknown')}`")
    st.sidebar.write(f"Streamlit Cloud: `{context.is_cloud}`")
    st.sidebar.write(f"HYDROLITE_SWMM_PYTHON: `{'detected' if context.swmm_python_detected else 'not detected'}`")
    st.sidebar.write(f"GEE_PROJECT: `{'detected' if context.gee_project_detected else 'not detected'}`")
    st.sidebar.write(f"项目根目录: `{PROJECT_ROOT}`")
    if context.is_cloud:
        st.sidebar.info("云端可展示已有结果；SWMM/GEE/OpenHydroNet 后端不可用时会优雅降级。")


def main() -> None:
    st.set_page_config(page_title="HydroLite Studio", layout="wide")
    project_dir = _sidebar_project_selector()
    context = load_workbench_context(project_dir)
    _sidebar_status(context)

    page_name = st.sidebar.radio("主导航", list(PAGES.keys()))
    st.title("HydroLite Studio 工作台")
    st.caption("项目化水文水动力建模、数据校验、GEE 数据产品、SWMM 联动、AI 输入包与报告导出。")

    if not context.project_loaded:
        st.warning(context.error_message)
        st.info("不会自动覆盖已有项目。请确认项目路径，或用 CLI 创建项目。")

    PAGES[page_name](context)


if __name__ == "__main__":
    main()
