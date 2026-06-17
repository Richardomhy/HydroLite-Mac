from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.data_templates import (
    export_all_data_templates,
    list_data_templates,
    validate_project_input_dataset,
    write_data_template_summary,
)
from hydrolite.ui.components import show_download
from hydrolite.ui.state import PROJECT_ROOT, WorkbenchContext


def _safe_export_path(path_text: str, context: WorkbenchContext) -> tuple[bool, Path, str]:
    path = Path(path_text).expanduser()
    resolved = path if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    if context.is_cloud:
        try:
            resolved.relative_to(PROJECT_ROOT)
        except ValueError:
            return False, resolved, "Streamlit Cloud 环境下仅允许导出到项目根目录内的路径。"
    if "data_raw" in resolved.parts:
        return False, resolved, "不能将模板导出到 data_raw。"
    return True, resolved, ""


def render(context: WorkbenchContext) -> None:
    st.header("数据模板")
    st.caption("下载真实工程项目数据模板，检查 CSV/GeoJSON 字段、单位和基础合理性。")
    st.info("真实项目建议先下载 `templates/data` 标准模板，整理数据后再使用项目向导创建项目。")

    templates = list_data_templates()
    table = pd.DataFrame(
        [
            {
                "template_name": row["template_name"],
                "description": row["description"],
                "required_fields": ", ".join(row["required_fields"]) or "GeoJSON Polygon/MultiPolygon",
                "numeric_fields": ", ".join(row["numeric_fields"]),
                "time_fields": ", ".join(row["time_fields"]),
            }
            for row in templates
        ]
    )
    st.subheader("模板列表与字段说明")
    st.dataframe(table, use_container_width=True, hide_index=True)

    st.subheader("模板下载")
    for row in templates:
        cols = st.columns([2, 2, 3])
        cols[0].write(f"**{row['template_name']}**")
        show_download(f"下载 {Path(row['template_path']).name}", row["template_path"], "text/csv")
        if row["example_path"]:
            show_download(f"下载示例 {Path(row['example_path']).name}", row["example_path"], "text/csv")

    st.subheader("一键导出全部模板")
    export_dir_text = st.text_input("导出目录", value="templates_export")
    safe, export_dir, message = _safe_export_path(export_dir_text, context)
    if not safe:
        st.error(message)
    if st.button("导出全部模板", disabled=not safe, use_container_width=True):
        try:
            paths = export_all_data_templates(export_dir)
            outputs = write_data_template_summary(export_dir)
            st.success(f"已导出 {len(paths)} 个模板文件。")
            st.json({"summary_md": str(outputs["md"]), "summary_xlsx": str(outputs["xlsx"])})
        except Exception as exc:
            st.error(f"导出失败: {exc}")

    st.subheader("校验数据目录")
    default_dataset = "templates/data/examples"
    dataset_text = st.text_input("数据目录路径", value=default_dataset)
    dataset_path = Path(dataset_text).expanduser()
    dataset_path = dataset_path if dataset_path.is_absolute() else (PROJECT_ROOT / dataset_path).resolve()
    if st.button("校验数据目录", use_container_width=True):
        try:
            result = validate_project_input_dataset(dataset_path)
            st.metric("校验状态", result["status"])
            rows = []
            for check in result["checks"]:
                rows.append(
                    {
                        "template_name": check["template_name"],
                        "status": check["status"],
                        "rows": check["rows"],
                        "fields": ", ".join(check["fields"]),
                        "errors": "; ".join(check["errors"]),
                        "warnings": "; ".join(check["warnings"]),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"校验失败: {exc}")

    st.subheader("模板使用建议")
    st.markdown(
        """
- 从 Excel 另存为 UTF-8 CSV 后，再检查字段名是否与模板完全一致。
- 面积单位使用 `km2`，流量使用 `cms`，降雨使用 `mm`，时间建议使用 ISO 风格。
- `cn` 建议满足 `0 < cn <= 100`，`muskingum_x` 必须满足 `0 <= X <= 0.5`。
- `basin_boundary.geojson` 只要求 Polygon/MultiPolygon 可解析；复杂 GIS 拓扑请在专业 GIS 软件中提前检查。
- 整理完成后，在 `项目向导` 页面引用这些文件生成项目。
"""
    )

    show_download("下载 data_template_summary.md", export_dir / "data_template_summary.md", "text/markdown")
    show_download(
        "下载 data_template_summary.xlsx",
        export_dir / "data_template_summary.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
