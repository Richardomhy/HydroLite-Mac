from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import streamlit as st

from hydrolite.connectors import list_connectors
from hydrolite.data_acquisition import create_acquisition_plan, write_acquisition_report, import_fetched_dataset
from hydrolite.connectors.contracts import DataRequirement
from hydrolite.data_center import write_data_center_reports
from hydrolite.data_quality_center import run_workspace_quality_checks, write_data_quality_report
from hydrolite.data_registry import list_dataset_types, write_data_registry_report
from hydrolite.data_requirements import build_project_data_requirement_matrix, write_data_readiness_report
from hydrolite.data_requirement_resolver import resolve_scenario_requirements, write_resolution, fetch_recommended
from hydrolite.connectors.registry import DataConnectorRegistry
from hydrolite.data_upload import copy_upload_to_workspace, inspect_uploaded_file, preview_uploaded_dataset
from hydrolite.input_builder import build_all_inputs
from hydrolite.data_lineage import validate_lineage_graph, write_lineage_report
from hydrolite.workspace import create_workspace, inspect_workspace, list_workspace_datasets
from hydrolite.ui.state import PROJECT_ROOT, WorkbenchContext, load_app_state


OUTPUT = PROJECT_ROOT / "output" / "data_center"
ACQUISITION_STATUS_LABELS = {
    "local_ready": "Local",
    "auto_fetch_available": "Auto Fetch",
    "approval_required": "Review",
    "project_measurement_required": "User Required",
    "unavailable": "User Required",
    "network_blocked": "Network Blocked",
    "fetched": "Downloaded · QC required",
    "cached": "Cached · QC required",
    "offline_cached": "Cached · QC required",
    "invalid_content_type": "Failed · file type check",
    "checksum_mismatch": "Failed · checksum check",
    "authentication_required": "Authentication Required",
    "auth_required": "Authentication Required",
    "non_public_resolution": "Blocked by Security",
    "dns_failure": "Failed · DNS",
    "proxy_blocked": "Failed · proxy",
    "tls_failure": "Failed · TLS",
    "remote_unavailable": "Failed · provider unavailable",
    "size_limit": "Approval Required · size limit",
    "discover_only": "Discovery only",
}


def acquisition_status_label(status: str) -> str:
    return ACQUISITION_STATUS_LABELS.get(status, "Failed" if status.endswith(("failed", "error")) else status.replace("_", " ").title())


def _safe_workspace(value: str, context: WorkbenchContext) -> tuple[Path, bool]:
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    allowed = PROJECT_ROOT / ("output" if context.is_cloud else "workspaces")
    safe = allowed.resolve() in resolved.parents or resolved == allowed.resolve()
    return resolved, safe and "data_raw" not in resolved.parts


def _provider_source_rows():
    from hydrolite.connectors.registry import DataConnectorRegistry, provider_profiles
    health = {row["connector_id"]: row for row in DataConnectorRegistry().health()}
    aliases = {"earth_engine": "gee"}
    rows = []
    for profile in provider_profiles().values():
        connector_id = aliases.get(profile["provider_id"], profile["provider_id"])
        status = health.get(connector_id, {}).get("status", "unavailable")
        rows.append({"Provider": profile["provider_name"], "Authority": profile["authority"],
                     "Status": status, "Data types": ", ".join(profile["supported_data_types"]),
                     "Discovery": profile["search_supported"], "Auto fetch": profile["fetch_supported"],
                     "Authentication": profile["authentication"], "License": profile["license_status"],
                     "Commercial use": profile["commercial_use_status"], "Endpoint": profile["base_endpoint"]})
    return rows


def render(context: WorkbenchContext) -> None:
    st.header("数据中心")
    st.caption("真实项目数据上传、识别、字段映射、质量校验、血缘、外部数据计划与模型输入准备。")
    st.warning("原始上传文件保持只读；只有通过质量检查的 standardized/derived 数据可进入模型输入。")
    state = load_app_state(st.session_state)
    if state.ui_mode == "simple":
        tabs = st.tabs(["数据概况", "完整度", "问题", "需要操作", "数据来源"])
        with tabs[0]:
            if context.project_loaded: st.json({"project": context.project_name, "directories": context.directories, "case_count": len(context.cases)})
            else: st.info("没有项目。请先在项目页面创建或打开项目。")
        with tabs[1]: st.info("数据完整度按当前场景的 Required Data / Optional Data 计算。请进入场景页面选择任务。")
        with tabs[2]: st.info("问题状态包括 Missing、Invalid、Needs Mapping、Needs Unit Fix 和 Needs CRS Fix。")
        with tabs[3]: st.info("下一步建议：先选择场景，再处理缺失数据；可自动修复项会明确标记，原始上传保持只读。")
        with tabs[4]:
            st.dataframe(pd.DataFrame(_provider_source_rows()), use_container_width=True, hide_index=True)
            st.caption("公开元数据发现不等于可自动下载；公开遥感/再分析不等于项目实测。")
        return
    workspace_value = st.text_input("工作区路径", value="output/demo_workspace" if context.is_cloud else "workspaces/real_project")
    project_name = st.text_input("项目名称", value="Real Project")
    workspace, safe = _safe_workspace(workspace_value, context)
    if not safe:
        st.error("工作区必须位于本地 workspaces/ 或云端 output/ 下，且不能位于 data_raw。")

    tabs = st.tabs(["项目", "上传", "字段映射", "数据质量", "GEE", "Earthdata", "Copernicus", "STAC", "数据需求", "模型输入", "血缘", "下载与报告", "数据来源"])
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
        workflow = st.selectbox("应用场景", ["full_modeling_workflow", "watershed_hydrology", "hydrolite_event_model", "flood_forecast", "drought_monitoring", "SC01", "SC02", "SC03", "SC05", "SC09", "SC10", "water_environment_source_accounting"])
        online = st.checkbox("允许查询已配置的官方公开元数据端点", value=False, help="只查询公开元数据；GEE 计算/导出认证另行处理，NASA 下载可能需要 Earthdata Login。")
        context = {}
        if online:
            bbox_text = st.text_input("检索范围 bbox（W,S,E,N）", placeholder="例如 -122.5,37.7,-122.4,37.8")
            dates_text = st.text_input("时间范围（可选，ISO start,end）", placeholder="2024-01-01,2024-12-31")
            resolution = st.number_input("最大像元尺寸（米，可选）", min_value=0.0, value=0.0, step=10.0)
            if bbox_text.strip():
                try:
                    context["bbox"] = [float(value.strip()) for value in bbox_text.split(",")]
                    if len(context["bbox"]) != 4:
                        raise ValueError
                except ValueError:
                    st.error("bbox 需要四个数值：W,S,E,N。")
                    context.pop("bbox", None)
            if dates_text.strip():
                values = [value.strip() for value in dates_text.split(",")]
                if len(values) == 2:
                    context["dates"] = values
                else:
                    st.error("时间范围需要两个逗号分隔的 ISO 日期。")
            if resolution > 0:
                context["maximum_resolution_m"] = resolution
        if st.button("解析本地数据与数据需求", disabled=not workspace.exists()):
            resolution = resolve_scenario_requirements(workflow, workspace, online=online, context=context)
            target = workspace / "reports" / "data_requirements" / workflow
            write_resolution(resolution, target)
            st.session_state["data_requirement_resolution"] = resolution
            st.session_state["data_requirement_resolution_path"] = str(target)
        resolution = st.session_state.get("data_requirement_resolution")
        if resolution and resolution.get("scenario") == workflow:
            metrics = resolution["metrics"]
            st.caption(f"需求 {metrics['requirements_evaluated']} 项 · 本地就绪 {metrics['local_ready']} · 可自动获取 {metrics['auto_fetch']} · 在线候选 {metrics['online_candidate']} · 需项目补充 {metrics['user_required']}")
            st.caption(f"运行前置状态：{resolution['run_gate']}；此状态不会改变水文/水环境科学门禁。")
            frame = pd.DataFrame([{
                "需求": row["requirement"]["requirement_id"], "数据类型": row["requirement"]["data_type"],
                "策略": row.get("source_mode", row["strategy"]), "状态": acquisition_status_label(row["status"]), "本地数据": ", ".join(row.get("local_dataset_ids", [])),
                "候选数": len(row.get("candidates", [])), "说明": row["reason"],
            } for row in resolution["requirements"]])
            st.dataframe(frame, use_container_width=True, hide_index=True)
            required_data_path = workspace / "reports" / "data_requirements" / workflow / "user_required_data.xlsx"
            if required_data_path.is_file():
                st.download_button("下载项目必需数据清单", required_data_path.read_bytes(), file_name="user_required_data.xlsx", key="required_data_download")
            for row in resolution["requirements"]:
                for index, candidate in enumerate(row.get("candidates", [])):
                    with st.expander(f"{row['requirement']['requirement_id']} · {candidate['candidate']['dataset_id']} · {candidate['candidate']['provider']}"):
                        st.json({key: value for key, value in candidate.items() if key != "candidate"} | {"candidate": candidate["candidate"]})
                        st.caption("评分基于覆盖、时间、分辨率、变量、来源、许可与缺失度。下载后仍需进入 Data Center 完成标准化和 QC。")
                        if row["strategy"] == "AUTO_FETCH" and candidate.get("eligible") and candidate["candidate"].get("access_status") == "public_download":
                            confirm = st.checkbox("确认获取此公开候选到外部缓存", key=f"fetch_confirm_{workflow}_{row['requirement']['requirement_id']}_{index}")
                            estimated_size = candidate["candidate"].get("estimated_size")
                            large_confirm = False
                            if estimated_size and estimated_size > 50 * 1024 * 1024:
                                large_confirm = st.checkbox("确认该数据超过 50 MiB，允许最高 200 MiB 下载", key=f"fetch_large_confirm_{workflow}_{row['requirement']['requirement_id']}_{index}")
                            if st.button("获取并导入待 QC 数据", key=f"fetch_{workflow}_{row['requirement']['requirement_id']}_{index}", disabled=not confirm or (bool(estimated_size and estimated_size > 50 * 1024 * 1024) and not large_confirm)):
                                result = DataConnectorRegistry().fetch(candidate["candidate"], confirm_large=large_confirm)
                                if result.get("checksum"):
                                    result["data_center"] = import_fetched_dataset(result, workspace, DataRequirement(**row["requirement"]))
                                message = result.get("error_message")
                                if result.get("status") in {"fetched", "cached", "offline_cached"}:
                                    st.success(f"{acquisition_status_label(result['status'])}；已记录校验和。请继续运行 Data Center 标准化与 QC。")
                                    st.json({key: value for key, value in result.items() if key != "local_path"})
                                elif result.get("status") == "non_public_resolution":
                                    st.warning("数据源当前解析到非公网网络地址，为保护本机安全，HydroLite 已阻止连接。")
                                elif message:
                                    st.warning(f"{acquisition_status_label(result.get('status', 'failed'))}：{message}")
                                else:
                                    st.warning(acquisition_status_label(result.get("status", "failed")))
                        elif row["strategy"] == "AUTO_DISCOVER_REQUIRE_APPROVAL":
                            st.warning("该项只允许发现并人工审批；不会自动进入项目参数。")
                        elif candidate["candidate"].get("access_status") == "authentication_required":
                            st.info("目录可查；此计算/导出需要原有提供方认证。")
        if st.button("生成旧版完整度矩阵", disabled=not workspace.exists()):
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
    with tabs[12]:
        st.subheader("官方公开数据来源")
        st.dataframe(pd.DataFrame(_provider_source_rows()), use_container_width=True, hide_index=True)
        st.info("自动获取仅用于已核验许可、覆盖范围和体量的产品。需审批候选与项目必需资料分别展示，不会加入 Fetch All。")
        st.caption("GEE catalog metadata 与 compute authentication 分离；NASA CMR 搜索不等于可下载；Copernicus STAC 当前为发现候选；HydroSHEDS 每个产品须核对自身 license/attribution。")
