from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.batch import run_batch
from hydrolite.config import CaseConfig, load_case
from hydrolite.runner import run_case
from hydrolite.swmm.runner import read_swmm_summary


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = PROJECT_ROOT / "cases"
OUTPUT_ROOT = PROJECT_ROOT / "output"


def scan_case_files(cases_dir: str | Path = CASES_DIR) -> list[Path]:
    root = Path(cases_dir)
    return sorted([*root.glob("*.yaml"), *root.glob("*.yml")])


def output_dir_for_case(case_name: str) -> Path:
    return OUTPUT_ROOT / case_name


def read_result_flow(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
    return df


def read_summary(path: str | Path) -> pd.DataFrame:
    return pd.read_excel(path)


def read_water_balance(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    subbasin = pd.read_excel(path, sheet_name="subbasin_balance")
    outlet = pd.read_excel(path, sheet_name="outlet_balance")
    return subbasin, outlet


def read_swmm_outputs(swmm_dir: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(swmm_dir)
    outputs: dict[str, pd.DataFrame] = {}
    files = {
        "summary": root / "swmm_summary.xlsx",
        "kpis": root / "swmm_kpis.xlsx",
        "node_depth": root / "node_depth_timeseries.csv",
        "link_flow": root / "link_flow_timeseries.csv",
        "system": root / "system_timeseries.csv",
    }
    for key, path in files.items():
        if path.exists():
            outputs[key] = pd.read_excel(path) if path.suffix == ".xlsx" else pd.read_csv(path)
    return outputs


def load_existing_outputs(output_dir: Path) -> dict[str, Path]:
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
    }
    return {key: output_dir / name for key, name in names.items() if (output_dir / name).exists()}


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _case_display(config: CaseConfig) -> None:
    st.subheader("情景信息")
    st.metric("case_name", config.name)
    st.write(f"输入数据路径: `{config.input_dir}`")
    st.write("水文方法: `SCS-CN 产流 + 简化单位线汇流`")
    st.write("汇流方法: `Muskingum 河道汇流`")
    st.write(f"输出目录: `{output_dir_for_case(config.name)}`")
    st.write(f"SWMM enabled: `{config.swmm_enabled}`")
    if config.swmm_enabled:
        st.write(f"SWMM inp_file: `{config.swmm_inp_file}`")


def _show_result_flow(path: Path) -> None:
    df = read_result_flow(path)
    st.subheader("result_flow.csv")
    st.dataframe(df.head(200), use_container_width=True)

    time_col = "time" if "time" in df.columns else df.columns[0]
    flow_col = "outflow_cms" if "outflow_cms" in df.columns else df.select_dtypes("number").columns[-1]
    chart_df = df[[time_col, flow_col]].dropna()
    st.line_chart(chart_df.set_index(time_col), y=flow_col)

    peak_idx = int(df[flow_col].idxmax())
    peak_flow = float(df.loc[peak_idx, flow_col])
    peak_time = df.loc[peak_idx, time_col]
    total_volume = float(df[flow_col].sum() * 3600.0)
    c1, c2, c3 = st.columns(3)
    c1.metric("峰值流量", f"{peak_flow:.3f} m3/s")
    c2.metric("峰现时间", str(peak_time))
    c3.metric("总出流体积", f"{total_volume:.0f} m3")


def _show_water_balance(path: Path) -> None:
    subbasin, outlet = read_water_balance(path)
    st.subheader("water_balance.xlsx")
    st.write("subbasin_balance")
    st.dataframe(subbasin, use_container_width=True)
    st.write("outlet_balance")
    st.dataframe(outlet, use_container_width=True)

    warnings = []
    for label, df in (("subbasin_balance", subbasin), ("outlet_balance", outlet)):
        if "balance_error_percent" in df.columns:
            high = df[df["balance_error_percent"].abs() > 5]
            if not high.empty:
                warnings.append(f"{label} 存在超过 5% 的水量平衡误差。")
    for message in warnings:
        st.warning(message)


def _show_download(label: str, path: Path, mime: str) -> None:
    if path.exists():
        st.download_button(label, _read_bytes(path), file_name=path.name, mime=mime)


def _show_swmm_outputs(swmm_dir: Path, outputs: dict[str, Path]) -> None:
    tables = read_swmm_outputs(swmm_dir)
    summary = tables.get("summary", pd.DataFrame())
    kpis = tables.get("kpis", pd.DataFrame())

    st.subheader("SWMM 输出")
    if not summary.empty:
        row = summary.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("SWMM 状态", str(row.get("run_status", "")))
        c2.metric("backend_used", str(row.get("backend_used", "")))
        c3.metric("max_node_depth", str(row.get("max_node_depth", "")))
        c4, c5, c6 = st.columns(3)
        c4.metric("max_link_flow", str(row.get("max_link_flow", "")))
        c5.metric("total_flooding_volume", str(row.get("total_flooding_volume", "")))
        c6.metric("total_outflow_volume", str(row.get("total_outflow_volume", "")))
        st.dataframe(summary, use_container_width=True)

    if not kpis.empty:
        st.write("swmm_kpis.xlsx")
        st.dataframe(kpis, use_container_width=True)

    node_depth = tables.get("node_depth", pd.DataFrame())
    if not node_depth.empty:
        st.write("node_depth_timeseries.csv")
        st.dataframe(node_depth.head(200), use_container_width=True)
        if {"node_id", "depth"}.issubset(node_depth.columns):
            chart = node_depth.groupby("node_id", as_index=False)["depth"].max()
            st.bar_chart(chart.set_index("node_id"), y="depth")

    link_flow = tables.get("link_flow", pd.DataFrame())
    if not link_flow.empty:
        st.write("link_flow_timeseries.csv")
        st.dataframe(link_flow.head(200), use_container_width=True)
        if {"link_id", "flow"}.issubset(link_flow.columns):
            chart = link_flow.groupby("link_id", as_index=False)["flow"].max()
            st.bar_chart(chart.set_index("link_id"), y="flow")

    _show_download(
        "下载 swmm_summary.xlsx",
        outputs["swmm_summary"],
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    for key, label, mime in [
        ("swmm_kpis", "下载 swmm_kpis.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("swmm_node_depth", "下载 node_depth_timeseries.csv", "text/csv"),
        ("swmm_link_flow", "下载 link_flow_timeseries.csv", "text/csv"),
        ("swmm_system", "下载 system_timeseries.csv", "text/csv"),
    ]:
        if key in outputs:
            _show_download(label, outputs[key], mime)


def _show_case_outputs(config: CaseConfig) -> None:
    output_dir = output_dir_for_case(config.name)
    outputs = load_existing_outputs(output_dir)
    if not outputs:
        st.info("最近一次运行状态: 未发现输出结果")
        return

    st.success("最近一次运行状态: 已发现输出结果")
    if "hydrograph" in outputs:
        st.image(str(outputs["hydrograph"]), caption="hydrograph.png")
    if "result_flow" in outputs:
        _show_result_flow(outputs["result_flow"])
        _show_download("下载 result_flow.csv", outputs["result_flow"], "text/csv")
    if "summary" in outputs:
        st.subheader("summary.xlsx")
        st.dataframe(read_summary(outputs["summary"]), use_container_width=True)
        _show_download(
            "下载 summary.xlsx",
            outputs["summary"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if "water_balance" in outputs:
        _show_water_balance(outputs["water_balance"])
        _show_download(
            "下载 water_balance.xlsx",
            outputs["water_balance"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if "swmm_summary" in outputs:
        _show_swmm_outputs(output_dir / "swmm", outputs)


def _show_batch_summary() -> None:
    path = OUTPUT_ROOT / "batch_summary.xlsx"
    if not path.exists():
        return

    df = pd.read_excel(path)
    st.subheader("批量运行汇总")
    success_count = int((df["status"] == "success").sum()) if "status" in df.columns else 0
    failed_count = int((df["status"] == "failed").sum()) if "status" in df.columns else 0
    c1, c2 = st.columns(2)
    c1.metric("成功情景数", success_count)
    c2.metric("失败情景数", failed_count)
    st.dataframe(df, use_container_width=True)
    _show_download(
        "下载 batch_summary.xlsx",
        path,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def main() -> None:
    st.set_page_config(page_title="HydroLite-Mac", layout="wide")
    st.title("HydroLite-Mac")

    case_files = scan_case_files()
    if not case_files:
        st.error(f"未在 `{CASES_DIR}` 找到 .yaml 或 .yml 情景文件。")
        return

    st.sidebar.header("情景")
    selected = st.sidebar.selectbox(
        "选择情景",
        case_files,
        format_func=lambda path: path.name,
    )
    st.sidebar.write(f"情景文件路径: `{selected}`")

    config = load_case(selected)
    case_output_dir = output_dir_for_case(config.name)

    if st.sidebar.button("运行当前情景", use_container_width=True):
        try:
            run_case(selected, output_dir=case_output_dir)
            st.sidebar.success("当前情景运行完成")
        except Exception as exc:
            st.sidebar.error(f"当前情景运行失败: {exc}")

    if st.sidebar.button("批量运行全部情景", use_container_width=True):
        summary_path, rows, failed_cases = run_batch(CASES_DIR)
        st.sidebar.write(f"批量汇总: `{summary_path}`")
        if failed_cases:
            st.sidebar.error(f"失败情景数: {len(failed_cases)}")
        else:
            st.sidebar.success(f"全部情景运行完成: {len(rows)}")

    _case_display(config)
    _show_case_outputs(config)
    _show_batch_summary()


if __name__ == "__main__":
    main()
