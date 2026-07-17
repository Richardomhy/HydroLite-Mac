from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pandas as pd
import streamlit as st

from hydrolite.__version__ import __version__
from hydrolite.hec_hms import (
    analyze_reference_precipitation,
    build_hec_hms_diagnosis,
    build_hms_run_command,
    collect_hms_run_outputs,
    copy_hms_reference_project_to_output,
    create_calibrated_hms_project_from_hydrolite,
    create_hms_project_from_hydrolite,
    detect_hms_cli_modes,
    discover_hms_reference_projects,
    parse_hms_logs,
    run_hms_compute_probe,
    run_hms_open_probe,
    run_hms_probe,
    run_hms_project,
    run_official_hms_reference,
    select_smallest_hms_reference_project,
    summarize_hms_run,
    validate_hms_project,
    validate_hms_run_outputs,
    write_hec_hms_diagnosis,
    write_hms_dss_discovery_report,
    write_hms_official_validation_summary,
    write_hms_run_scripts,
)
from hydrolite.hec_hms_precipitation import (
    create_hms_rainfall_verified_project,
    evaluate_hms_rainfall_gate,
    map_project_rainfall,
    read_rainfall_context,
    run_hms_rainfall_compute,
    run_hms_rainfall_open_probe,
    validate_project_rainfall_dss,
    write_dss_backend_diagnosis,
    write_hms_rainfall_gate_report,
    write_hms_result_catalog_report,
    write_normalized_rainfall_report,
    write_project_rainfall_dss,
)
from hydrolite.hec_hms_format import compare_generated_to_reference, write_hms_format_comparison_report
from hydrolite.hec_hms_results import (
    DEFAULT_COMPARISON_DIR,
    DEFAULT_RESULTS_DIR,
    export_hms_comparison_bundle,
    load_hms_result_catalog,
    map_hms_results_to_hydrolite_elements,
    read_hms_dss_timeseries,
    run_hms_hydrolite_comparison,
    run_hms_result_extraction,
    validate_hms_comparison_outputs,
    write_hms_comparison_report,
)
from hydrolite.ui.components import read_text_if_exists, safe_read_excel, show_download, show_json
from hydrolite.ui.state import OUTPUT_ROOT, WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("HEC-HMS")
    st.caption(f"HydroLite Studio v{__version__}")
    st.warning("当前支持小型已完成事件的 DSS 结果读取和 HydroLite 对比，但不代表真实项目已完成率定。")

    diagnosis = build_hec_hms_diagnosis()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("HEC-HMS 安装", str(diagnosis["installation_detected"]))
    c2.metric("可执行文件", str(diagnosis["executable_detected"]))
    c3.metric("Java", str(diagnosis["java"]["available"]))
    c4.metric("推荐方式", diagnosis["recommended_integration"])
    st.write(f"Version: `{diagnosis['version_check']['stdout'] or diagnosis['version_check']['stderr']}`")
    st.write(f"Version method: `{diagnosis['version_check'].get('verification_method', 'unavailable')}`")
    if diagnosis["warnings"]:
        for warning in diagnosis["warnings"]:
            st.warning(warning)

    st.subheader("环境诊断")
    st.dataframe(pd.DataFrame(diagnosis["installations"]), use_container_width=True)
    st.dataframe(pd.DataFrame(diagnosis["executables"]), use_container_width=True)
    if st.button("运行 HMS 诊断", use_container_width=True):
        outputs = write_hec_hms_diagnosis()
        st.success(f"诊断已生成: `{outputs['md']}`")

    st.subheader("官方项目验证与格式校准")
    st.caption("官方示例项目仅复制到本机 output/ 用于验证，不会提交到仓库。Project.open 成功不代表模拟完成。")
    reference_root = OUTPUT_ROOT / "hec_hms_reference"
    reference_project = reference_root / "reference_project"
    verified_project = OUTPUT_ROOT / "hec_hms_project_verified"
    candidates = discover_hms_reference_projects()
    selected = select_smallest_hms_reference_project(candidates)
    official_candidates = [item for item in candidates if item.get("likely_official")]
    if official_candidates:
        st.dataframe(pd.DataFrame(official_candidates), use_container_width=True)
    else:
        st.info("未检测到官方项目，可继续使用 HydroLite 独立工作流和生成器语法检查。")
    if selected:
        st.write(
            f"已选择 `{selected['project_name']}`，大小 `{selected['total_size_bytes']}` bytes，"
            f"Run: `{', '.join(selected['run_names'])}`"
        )

    reference_cols = st.columns(4)
    if reference_cols[0].button("扫描官方参考项目", use_container_width=True):
        show_json({"candidates": candidates, "selected": selected})
    if reference_cols[1].button("复制参考项目到 output", disabled=selected is None, use_container_width=True):
        copied = copy_hms_reference_project_to_output(selected, reference_project)
        st.success(f"参考项目已复制: `{copied}`")
    if reference_cols[2].button("运行 reference open", disabled=not reference_project.exists(), use_container_width=True):
        show_json(run_official_hms_reference(reference_project, execute=False, timeout=60))
    confirm_reference_compute = st.checkbox("我理解：reference compute 会运行安装包官方小型样例，最长 120 秒。")
    if reference_cols[3].button(
        "运行 reference compute",
        disabled=not reference_project.exists() or not confirm_reference_compute,
        use_container_width=True,
    ):
        show_json(run_official_hms_reference(reference_project, execute=True, timeout=120))

    calibration_cols = st.columns(4)
    if calibration_cols[0].button("比较项目格式", disabled=not reference_project.exists(), use_container_width=True):
        comparison = compare_generated_to_reference(reference_project, OUTPUT_ROOT / "hec_hms_project")
        show_json({key: str(value) for key, value in write_hms_format_comparison_report(reference_root / "reports", comparison).items()})
    if calibration_cols[1].button("重新生成校准项目", use_container_width=True):
        show_json(create_calibrated_hms_project_from_hydrolite(context.project_dir, verified_project))
    if calibration_cols[2].button("运行 generated open-probe", disabled=not verified_project.exists(), use_container_width=True):
        show_json(run_hms_open_probe(verified_project))
    confirm_generated_compute = st.checkbox("我理解：仅当全部计算门禁通过时才会尝试 generated compute-probe。")
    if calibration_cols[3].button(
        "尝试 generated compute-probe",
        disabled=not verified_project.exists() or not confirm_generated_compute,
        use_container_width=True,
    ):
        show_json(run_hms_compute_probe(verified_project, execute=True, timeout=120))

    discovery_cols = st.columns(2)
    if discovery_cols[0].button("发现 DSS", disabled=not verified_project.exists(), use_container_width=True):
        show_json({key: str(value) for key, value in write_hms_dss_discovery_report(verified_project).items()})
    if discovery_cols[1].button("生成官方验证总表", use_container_width=True):
        show_json({key: str(value) for key, value in write_hms_official_validation_summary().items()})

    official_report = reference_root / "reports" / "hec_hms_official_reference_report.md"
    format_report = reference_root / "reports" / "hms_format_comparison.md"
    generated_open = verified_project / "reports" / "hec_hms_open_probe.md"
    generated_compute = verified_project / "reports" / "hec_hms_compute_probe.md"
    dss_report = verified_project / "reports" / "hec_hms_dss_discovery.md"
    for title, path in (
        ("官方参考验证", official_report),
        ("文件格式比较", format_report),
        ("生成项目 open-probe", generated_open),
        ("生成项目 compute-probe", generated_compute),
        ("DSS 发现", dss_report),
    ):
        text = read_text_if_exists(path)
        if text:
            with st.expander(title):
                st.markdown(text)
            show_download(f"下载 {path.name}", path, "text/markdown")

    st.subheader("降雨数据映射与最小计算")
    st.caption("当前为 HEC-HMS 4.13 最小项目验证，单次计算最长 120 秒，结果仍需人工复核。")
    rainfall_source = st.text_input(
        "降雨源项目",
        value=str(Path("projects/qgis_workflow_project").resolve()),
        key="hms_rainfall_source",
    )
    rainfall_project = Path(
        st.text_input(
            "降雨验证 HMS 项目",
            value=str(OUTPUT_ROOT / "hec_hms_project_rainfall_verified"),
            key="hms_rainfall_project",
        )
    ).expanduser().resolve()
    context_path = rainfall_project / "reports" / "hec_hms_rainfall_context.json"
    rainfall_context = read_rainfall_context(rainfall_project) if context_path.is_file() else {}
    gate_path = rainfall_project / "reports" / "hec_hms_rainfall_gate.json"
    compute_path = rainfall_project / "reports" / "hec_hms_rainfall_compute.json"
    gate_result = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.is_file() else {}
    compute_result = json.loads(compute_path.read_text(encoding="utf-8")) if compute_path.is_file() else {}
    metrics = st.columns(4)
    metrics[0].metric("降雨记录", rainfall_context.get("normalized_rows", 0))
    metrics[1].metric("时间步 (min)", rainfall_context.get("interval_minutes", "-"))
    metrics[2].metric("总降雨 (mm)", rainfall_context.get("total_precipitation_mm", "-"))
    metrics[3].metric("Rainfall gate", gate_result.get("status", "not_run"))
    if rainfall_context:
        st.write(f"rainfall.csv: `{rainfall_context.get('rainfall_csv', '')}`")
        st.write(f"Start / end: `{rainfall_context.get('start', '')}` / `{rainfall_context.get('end', '')}`")
        st.write(f"DSS backend: `{rainfall_context.get('dss_backend', '')}`")
        st.write(f"DSS pathname: `{rainfall_context.get('pathname', '')}`")
        st.write(f"DSS read-back: `{rainfall_context.get('dss_validation', {}).get('status', 'not_run')}`")
        mapping_overview = rainfall_context.get("mapping", {}).get("overview", {})
        st.write(
            f"Gage: `{mapping_overview.get('gage_name', '')}`; method: `{mapping_overview.get('meteorologic_method', '')}`; "
            f"mapped subbasins: `{mapping_overview.get('mapped_subbasins', '')}`"
        )
    if compute_result:
        st.write(
            f"Compute: `{compute_result.get('status', '')}`; result DSS: `{compute_result.get('result_dss', '')}`; "
            f"flow pathnames: `{len(compute_result.get('flow_pathnames', []))}`"
        )
        for error in compute_result.get("fatal_errors", []):
            st.error(error)
        for warning in compute_result.get("warnings", []):
            st.warning(warning)

    rainfall_buttons = [
        ("分析官方降雨结构", lambda: analyze_reference_precipitation()),
        ("检测 DSS 后端", lambda: {key: str(value) for key, value in write_dss_backend_diagnosis().items()}),
        ("规范化降雨", lambda: write_normalized_rainfall_report(rainfall_source)),
        ("创建降雨验证项目", lambda: create_hms_rainfall_verified_project(rainfall_source, rainfall_project)),
        ("写入 DSS", lambda: write_project_rainfall_dss(rainfall_source, rainfall_project)),
        ("验证 DSS", lambda: validate_project_rainfall_dss(rainfall_project)),
        ("映射降雨站", lambda: map_project_rainfall(rainfall_project)),
        ("检查 rainfall gate", lambda: _ui_rainfall_gate(rainfall_project)),
        ("Open-probe", lambda: run_hms_rainfall_open_probe(rainfall_project)),
        ("执行最小 computeRun", lambda: run_hms_rainfall_compute(rainfall_project, timeout=120)),
        ("生成结果 catalog", lambda: {key: str(value) for key, value in write_hms_result_catalog_report(rainfall_project).items()}),
    ]
    for row_start in range(0, len(rainfall_buttons), 3):
        button_columns = st.columns(3)
        for column, (label, action) in zip(button_columns, rainfall_buttons[row_start : row_start + 3]):
            if column.button(label, use_container_width=True, key=f"hms_rainfall_{row_start}_{label}"):
                try:
                    show_json(action())
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
    report_files = sorted((rainfall_project / "reports").glob("hec_hms_*")) if (rainfall_project / "reports").is_dir() else []
    if report_files:
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in report_files:
                if path.is_file():
                    archive.write(path, arcname=path.name)
        st.download_button("下载全部降雨验证报告", bundle.getvalue(), "hec_hms_rainfall_reports.zip", "application/zip")

    source_project = st.text_input("HydroLite 项目路径", value=str(context.project_dir))
    hms_output = st.text_input("HMS 项目输出目录", value=str(OUTPUT_ROOT / "hec_hms_project"))
    cols = st.columns(2)
    if cols[0].button("生成 HEC-HMS 项目骨架", use_container_width=True):
        try:
            result = create_hms_project_from_hydrolite(source_project, hms_output)
            st.success(f"项目骨架已生成，runnable_status: `{result['runnable_status']}`")
            show_json(result)
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
    if cols[1].button("校验 HMS 项目", use_container_width=True):
        show_json(validate_hms_project(hms_output))

    st.subheader("HEC-HMS 运行探测")
    st.caption("默认只生成 dry-run 报告。run-probe 不运行模拟，所有子进程均受 timeout 限制。")
    probe_cols = st.columns(3)
    if probe_cols[0].button("检测 CLI modes", use_container_width=True):
        show_json(detect_hms_cli_modes())
    if probe_cols[1].button("生成运行命令", use_container_width=True):
        show_json(build_hms_run_command(hms_output))
    if probe_cols[2].button("生成运行脚本", use_container_width=True):
        scripts = write_hms_run_scripts(hms_output)
        show_json({name: str(path) for name, path in scripts.items()})

    run_cols = st.columns(3)
    if run_cols[0].button("运行短时 probe", use_container_width=True):
        show_json(run_hms_probe())
    if run_cols[1].button("执行 dry-run", use_container_width=True):
        show_json(run_hms_project(hms_output, execute=False))
    confirm_execute = st.checkbox("我理解：这会尝试实际启动 HEC-HMS。当前功能为 MVP，结果需要人工复核。")
    if run_cols[2].button("尝试 execute", disabled=not confirm_execute, use_container_width=True):
        show_json(run_hms_project(hms_output, execute=True, timeout=60))

    output_cols = st.columns(3)
    if output_cols[0].button("收集 HMS 输出", use_container_width=True):
        show_json(collect_hms_run_outputs(hms_output))
    if output_cols[1].button("解析 HMS 日志", use_container_width=True):
        show_json(parse_hms_logs(hms_output))
    if output_cols[2].button("校验运行输出", use_container_width=True):
        show_json(validate_hms_run_outputs(hms_output))
    if st.button("重新生成运行摘要", use_container_width=True):
        show_json(summarize_hms_run(hms_output))

    diagnosis_dir = OUTPUT_ROOT / "hec_hms"
    diagnosis_md = diagnosis_dir / "hec_hms_diagnosis.md"
    diagnosis_json = diagnosis_dir / "hec_hms_diagnosis.json"
    root = Path(hms_output)
    report = root / "reports" / "hec_hms_project_report.md"
    manifest = root / "reports" / "hec_hms_project_manifest.json"
    mappings = root / "reports" / "hec_hms_mapping_summary.xlsx"
    run_report = root / "reports" / "hec_hms_run_report.md"
    run_result = root / "reports" / "hec_hms_run_result.json"
    run_summary = root / "reports" / "hec_hms_run_summary.xlsx"
    run_shell = root / "scripts" / "run_hms.sh"
    run_batch = root / "scripts" / "run_hms.bat"
    run_jython = root / "scripts" / "hydrolite_run_hms.py"

    st.subheader("HEC-HMS 诊断报告")
    diagnosis_text = read_text_if_exists(diagnosis_md)
    if diagnosis_text:
        st.markdown(diagnosis_text)
    else:
        st.info("点击“运行 HMS 诊断”生成报告。")

    st.subheader("HEC-HMS 项目报告")
    report_text = read_text_if_exists(report)
    if report_text:
        st.markdown(report_text)
    else:
        st.info("尚未生成 HEC-HMS 项目骨架。")
    mapping_summary = safe_read_excel(mappings, "summary")
    if not mapping_summary.empty:
        st.dataframe(mapping_summary, use_container_width=True)

    st.subheader("HEC-HMS 运行报告")
    run_report_text = read_text_if_exists(run_report)
    if run_report_text:
        st.markdown(run_report_text)
    else:
        st.info("尚未生成运行报告，请先执行 dry-run。")
    run_result_text = read_text_if_exists(run_result)
    if run_result_text:
        st.code(run_result_text, language="json")
    run_overview = safe_read_excel(run_summary, "overview")
    if not run_overview.empty:
        st.dataframe(run_overview, use_container_width=True)

    show_download("下载 hec_hms_diagnosis.md", diagnosis_md, "text/markdown")
    show_download("下载 hec_hms_diagnosis.json", diagnosis_json, "application/json")
    show_download("下载 hec_hms_project_manifest.json", manifest, "application/json")
    show_download("下载 hec_hms_mapping_summary.xlsx", mappings, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    show_download("下载 hec_hms_run_report.md", run_report, "text/markdown")
    show_download("下载 hec_hms_run_result.json", run_result, "application/json")
    show_download("下载 hec_hms_run_summary.xlsx", run_summary, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    show_download("下载 run_hms.sh", run_shell, "text/x-shellscript")
    show_download("下载 run_hms.bat", run_batch, "text/plain")
    show_download("下载 hydrolite_run_hms.py", run_jython, "text/x-python")

    st.subheader("HEC-HMS 结果与 HydroLite 对比")
    st.caption("本区域展示两个模型对同一事件的模拟差异，不代表任何一个模型已完成真实项目率定。")
    result_hms_project = rainfall_project
    result_hydro_project = Path(rainfall_source).expanduser().resolve()
    result_dss = result_hms_project / "hydrolite_run.dss"
    result_columns = st.columns(4)
    if result_columns[0].button("读取 DSS catalog", disabled=not result_dss.is_file(), use_container_width=True):
        show_json(load_hms_result_catalog(result_dss))
    if result_columns[1].button("读取全部流量过程", disabled=not result_dss.is_file(), use_container_width=True):
        catalog = load_hms_result_catalog(result_dss)
        result = read_hms_dss_timeseries(result_dss, catalog["flow_pathnames"], DEFAULT_RESULTS_DIR, timeout=60)
        show_json({key: result[key] for key in ("status", "backend", "successful_pathname_count", "failed_pathname_count")})
    if result_columns[2].button("映射 HMS/HydroLite 元素", disabled=not result_dss.is_file(), use_container_width=True):
        show_json(map_hms_results_to_hydrolite_elements(result_hms_project, load_hms_result_catalog(result_dss), result_hydro_project))
    if result_columns[3].button("运行结果提取", disabled=not result_dss.is_file(), use_container_width=True):
        show_json(run_hms_result_extraction(result_hms_project, DEFAULT_RESULTS_DIR))

    compare_columns = st.columns(4)
    if compare_columns[0].button("识别出口", disabled=not result_dss.is_file(), use_container_width=True):
        extracted = run_hms_result_extraction(result_hms_project, DEFAULT_RESULTS_DIR)
        show_json(extracted["outlet_selection"])
    if compare_columns[1].button("运行 HydroLite 对比", disabled=not result_dss.is_file(), use_container_width=True):
        show_json(run_hms_hydrolite_comparison(result_hms_project, result_hydro_project, DEFAULT_COMPARISON_DIR))
    if compare_columns[2].button("生成对比报告", disabled=not (DEFAULT_COMPARISON_DIR / "comparison_manifest.json").is_file(), use_container_width=True):
        st.success(f"报告已生成: `{write_hms_comparison_report(DEFAULT_COMPARISON_DIR)}`")
    if compare_columns[3].button("生成对比 bundle", disabled=not (DEFAULT_COMPARISON_DIR / "comparison_report.md").is_file(), use_container_width=True):
        st.success(f"Bundle 已生成: `{export_hms_comparison_bundle(DEFAULT_COMPARISON_DIR)}`")

    comparison_book = DEFAULT_COMPARISON_DIR / "model_comparison_metrics.xlsx"
    comparison_summary = safe_read_excel(comparison_book, "summary")
    comparison_metrics = safe_read_excel(comparison_book, "comparison_metrics")
    if not comparison_summary.empty:
        st.dataframe(comparison_summary, use_container_width=True)
        st.dataframe(comparison_metrics, use_container_width=True)
        summary_row = comparison_summary.iloc[0]
        metric_row = comparison_metrics.iloc[0] if not comparison_metrics.empty else {}
        display = st.columns(4)
        display[0].metric("Comparison status", summary_row.get("comparison_status", "unknown"))
        display[1].metric("NSE", f"{metric_row.get('NSE', float('nan')):.3f}" if pd.notna(metric_row.get("NSE")) else "NA")
        display[2].metric("KGE", f"{metric_row.get('KGE', float('nan')):.3f}" if pd.notna(metric_row.get("KGE")) else "NA")
        display[3].metric("RMSE", f"{metric_row.get('RMSE', float('nan')):.3f}" if pd.notna(metric_row.get("RMSE")) else "NA")
        for chart in sorted((DEFAULT_COMPARISON_DIR / "charts").glob("*.png")):
            st.image(str(chart), caption=chart.stem, use_container_width=True)
    comparison_report = DEFAULT_COMPARISON_DIR / "comparison_report.md"
    comparison_text = read_text_if_exists(comparison_report)
    if comparison_text:
        with st.expander("查看对比报告"):
            st.markdown(comparison_text)
    for label, path, mime in (
        ("下载对齐 CSV", DEFAULT_COMPARISON_DIR / "aligned_outlet_timeseries.csv", "text/csv"),
        ("下载指标 Excel", comparison_book, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("下载对比报告", comparison_report, "text/markdown"),
        ("下载对比 bundle", DEFAULT_COMPARISON_DIR / "hec_hms_comparison_bundle.zip", "application/zip"),
    ):
        show_download(label, path, mime)
    validation_result = validate_hms_comparison_outputs(DEFAULT_COMPARISON_DIR) if comparison_book.is_file() else None
    if validation_result and validation_result["status"] != "passed":
        st.warning(validation_result)

    st.info("推荐下一步：在 HEC-HMS 4.13 中人工打开并复核 basin/met/control/run 文件、连通性、单位和参数；验证前不执行生产计算。")


def _ui_rainfall_gate(project_dir: Path) -> dict:
    result = evaluate_hms_rainfall_gate(project_dir)
    write_hms_rainfall_gate_report(project_dir, result)
    return result
