from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.calibration import (
    DEFAULT_OUTPUT,
    compare_best_case,
    create_calibrated_case,
    export_calibration_bundle,
    run_oat_sensitivity,
    run_parameter_search,
    run_calibrated_case,
    select_calibration_target,
    select_best_calibration_candidate,
    write_calibration_report,
    write_parameter_outputs,
    write_target_outputs,
)
from hydrolite.ui.components import safe_read_excel, show_download
from hydrolite.ui.state import WorkbenchContext, is_streamlit_cloud


def render(context: WorkbenchContext) -> None:
    st.header("参数率定与敏感性")
    st.warning("当前项目没有独立实测验证时，本功能只执行单事件跨模型对齐，不能替代真实流量率定。")
    output = DEFAULT_OUTPUT
    hms = Path("output/hec_hms_comparison")
    target = select_calibration_target(context.project_dir, hms)
    st.write(f"目标模式: `{target['target_mode']}` | 来源: `{target['target_source']}`")
    st.caption(f"术语: {target['terminology_to_use']}; synthetic: {target.get('observed_is_synthetic', False)}")
    for warning in target.get("warnings", []):
        st.warning(warning)
    columns = st.columns(3)
    if columns[0].button("生成目标与参数表", use_container_width=True):
        write_target_outputs(context.project_dir, hms, output)
        write_parameter_outputs(context.project_dir, output)
        st.success("已生成 calibration target、baseline parameters 与 bounds。")
    candidates = columns[1].number_input("搜索候选数量", min_value=1, max_value=10 if is_streamlit_cloud() else 40, value=10 if is_streamlit_cloud() else 30)
    if columns[2].button("运行受控参数搜索", use_container_width=True):
        _, bounds = write_parameter_outputs(context.project_dir, output)
        result = run_parameter_search(context.project_dir, target, bounds, output / "search", int(candidates))
        st.success(f"搜索完成: {len(result['ranked'])}/{len(result['results'])} candidates succeeded")
    if st.button("运行单因素敏感性", use_container_width=True):
        _, bounds = write_parameter_outputs(context.project_dir, output)
        result = run_oat_sensitivity(context.project_dir, target, bounds, output / "sensitivity")
        st.success(f"敏感性完成: {len(result['results'])} candidates")
    ranking_path = output / "search" / "candidate_ranking.xlsx"
    if ranking_path.exists():
        actions = st.columns(4)
        if actions[0].button("生成最佳情景", use_container_width=True):
            best = select_best_calibration_candidate(pd.read_excel(ranking_path))
            created = create_calibrated_case(context.project_dir, best, context.project_dir / "cases" / "qgis_demo_aligned.yaml")
            st.success(f"已生成: {created['case']}")
        if actions[1].button("运行最佳情景", use_container_width=True):
            result = run_calibrated_case(context.project_dir / "cases" / "qgis_demo_aligned.yaml")
            st.success(f"运行完成: {result.output_dir}")
        if actions[2].button("对齐 HEC-HMS", use_container_width=True):
            result = compare_best_case(context.project_dir, Path("output/hec_hms_project_rainfall_verified"))
            st.success(f"对齐报告: {result['report']}")
        if actions[3].button("生成并导出报告", use_container_width=True):
            write_calibration_report(output)
            bundle = export_calibration_bundle(output)
            st.success(f"已生成: {bundle}")
    for title, path, sheet in (
        ("当前参数", output / "baseline_parameters.xlsx", 0),
        ("参数边界", output / "parameter_bounds.xlsx", 0),
        ("候选排名", output / "search" / "candidate_ranking.xlsx", 0),
        ("敏感性排名", output / "sensitivity" / "parameter_sensitivity.xlsx", 0),
    ):
        if path.exists():
            st.subheader(title)
            st.dataframe(safe_read_excel(path, sheet), use_container_width=True)
            show_download(f"下载 {path.name}", path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for chart in sorted((output / "search" / "charts").glob("*.png")) + sorted((output / "sensitivity" / "charts").glob("*.png")):
        st.image(str(chart), caption=chart.name)
    if (output / "calibration_bundle.zip").exists():
        show_download("下载 calibration_bundle.zip", output / "calibration_bundle.zip", "application/zip")
