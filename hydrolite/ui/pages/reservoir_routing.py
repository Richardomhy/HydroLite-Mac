from pathlib import Path
import streamlit as st
from hydrolite.reservoir_routing import run_reservoir_demo
from hydrolite.ui.components import safe_read_csv, safe_read_excel, show_download
from hydrolite.ui.state import WorkbenchContext

ROOT=Path(__file__).resolve().parents[3]
def render(context: WorkbenchContext)->None:
    st.header("水库调蓄")
    st.warning("ICESat-2 水深仅是沿轨约束；实际调蓄仍需要可靠库容曲线、泄流曲线和调度资料。库容曲线不等于泄流曲线。")
    if st.button("运行原创水库 Demo"): st.success(str(run_reservoir_demo()["paths"]["report"]))
    root=ROOT/"output/reservoir"
    for name in ("reservoir_routing_summary.xlsx","reservoir_routing_timeseries.csv"):
        p=root/name
        if p.exists():
            st.subheader(name);st.dataframe(safe_read_excel(p) if p.suffix==".xlsx" else safe_read_csv(p),use_container_width=True);show_download("下载 "+name,p,"application/octet-stream")
    st.caption("HEC-HMS Reservoir 仅在项目 open 和 paired-data 门禁通过后才可计算；当前 demo 会安全跳过未验证计算。")
    st.info("本机 4.13 官方 river_bend 示例已用于 paired-data 结构诊断；其 DSS 工作副本不可访问时，compute 保持禁用。洪水预测仍为 planned。")
