from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.__version__ import __version__
from hydrolite.hec_hms import (
    build_hec_hms_diagnosis,
    build_hms_run_command,
    collect_hms_run_outputs,
    create_hms_project_from_hydrolite,
    detect_hms_cli_modes,
    parse_hms_logs,
    run_hms_probe,
    run_hms_project,
    summarize_hms_run,
    validate_hms_project,
    validate_hms_run_outputs,
    write_hec_hms_diagnosis,
    write_hms_run_scripts,
)
from hydrolite.ui.components import read_text_if_exists, safe_read_excel, show_download, show_json
from hydrolite.ui.state import OUTPUT_ROOT, WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("HEC-HMS")
    st.caption(f"HydroLite Studio v{__version__}")
    st.warning("当前为 HEC-HMS 环境诊断与项目生成 MVP，不等于已完成真实 HMS 模拟或 DSS 结果读取。")

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

    st.info("推荐下一步：在 HEC-HMS 4.13 中人工打开并复核 basin/met/control/run 文件、连通性、单位和参数；验证前不执行生产计算。")
