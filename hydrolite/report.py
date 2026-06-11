from __future__ import annotations

from pathlib import Path

import pandas as pd


def _format_value(value: object) -> str:
    if pd.isna(value):
        return "NA"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _best_row(df: pd.DataFrame, column: str, absolute: bool = False) -> pd.Series | None:
    if df.empty or column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce")
    if absolute:
        values = values.abs()
    if values.dropna().empty:
        return None
    return df.loc[values.idxmax()]


def _markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> str:
    if df.empty:
        return "暂无可用数据。"
    usable = [column for column in columns if column in df.columns]
    if not usable:
        return "暂无可用数据。"
    table = df[usable].head(max_rows).copy()
    header = "| " + " | ".join(usable) + " |"
    separator = "| " + " | ".join("---" for _ in usable) + " |"
    rows = []
    for _, row in table.iterrows():
        rows.append("| " + " | ".join(_format_value(row[column]) for column in usable) + " |")
    return "\n".join([header, separator, *rows])


def build_report(
    output_path: str | Path,
    tables: dict[str, pd.DataFrame],
    generated_files: dict[str, Path],
) -> Path:
    path = Path(output_path)
    overview = tables.get("overview", pd.DataFrame())
    hydrology = tables.get("hydrology_metrics", pd.DataFrame())
    water_balance = tables.get("water_balance_metrics", pd.DataFrame())
    swmm = tables.get("swmm_metrics", pd.DataFrame())
    coupling = tables.get("coupling_metrics", pd.DataFrame())

    conclusions: list[str] = []
    peak_row = _best_row(hydrology, "peak_flow")
    if peak_row is not None:
        conclusions.append(
            f"- 峰值流量最大的情景为 `{peak_row.get('case_name')}`，峰值流量 "
            f"{_format_value(peak_row.get('peak_flow'))} m3/s。"
        )
    volume_row = _best_row(hydrology, "total_runoff_volume_m3")
    if volume_row is not None:
        conclusions.append(
            f"- 总径流量最大的情景为 `{volume_row.get('case_name')}`，总量 "
            f"{_format_value(volume_row.get('total_runoff_volume_m3'))} m3。"
        )
    balance_row = _best_row(water_balance, "outlet_balance_error_percent", absolute=True)
    if balance_row is not None:
        conclusions.append(
            f"- 水量平衡误差最大的情景为 `{balance_row.get('case_name')}`，出口误差 "
            f"{_format_value(balance_row.get('outlet_balance_error_percent'))}%。"
        )
    node_row = _best_row(swmm, "max_node_depth")
    if node_row is not None:
        conclusions.append(
            f"- SWMM 最大节点水深对应情景为 `{node_row.get('case_name')}`，水深 "
            f"{_format_value(node_row.get('max_node_depth'))}。"
        )
    link_row = _best_row(swmm, "max_link_flow")
    if link_row is not None:
        conclusions.append(
            f"- SWMM 最大管道流量对应情景为 `{link_row.get('case_name')}`，流量 "
            f"{_format_value(link_row.get('max_link_flow'))}。"
        )
    if not coupling.empty and "coupling_status" in coupling.columns:
        failed = coupling[coupling["coupling_status"].astype(str).str.lower() == "failed"]
        if not failed.empty:
            cases = ", ".join(f"`{name}`" for name in failed["case_name"].astype(str))
            conclusions.append(f"- 存在 HydroLite-SWMM coupling failed 情景：{cases}。")
    if not overview.empty and "run_status" in overview.columns:
        statuses = overview["run_status"].astype(str).str.lower()
        if not statuses.empty and (statuses == "success").all():
            conclusions.append("- 所有情景运行成功。")
    if not conclusions:
        conclusions.append("- 当前输出不足以形成稳定自动摘要，请先运行情景或批量任务。")

    files = "\n".join(f"- `{label}`: `{file_path}`" for label, file_path in generated_files.items())
    content = f"""# HydroLite-Mac 情景对比自动报告

## 项目概况

本报告由 `python -m hydrolite compare output/` 自动生成，用于汇总 HydroLite 水文结果、Muskingum 汇流结果、水量平衡结果、SWMM 结果和 HydroLite-SWMM coupling 状态。

## 情景列表

{_markdown_table(overview, ["case_name", "run_status", "has_hydrolite_result", "has_water_balance", "has_swmm", "has_coupling", "notes"])}

## HydroLite 水文结果对比

{_markdown_table(hydrology, ["case_name", "peak_flow", "peak_time", "total_runoff_volume_m3"])}

## 水量平衡对比

{_markdown_table(water_balance, ["case_name", "max_subbasin_balance_error_percent", "outlet_balance_error_percent"])}

## SWMM 结果对比

{_markdown_table(swmm, ["case_name", "swmm_status", "backend_used", "max_node_depth", "max_link_flow", "total_flooding_volume", "total_outflow_volume"])}

## HydroLite-SWMM coupling 状态

{_markdown_table(coupling, ["case_name", "coupling_enabled", "coupling_status", "target_node", "inflow_name", "timeseries_points", "max_flow", "total_inflow_volume_m3"])}

## 主要结论自动摘要

{chr(10).join(conclusions)}

## 文件清单

{files}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
