from pathlib import Path
import streamlit as st
from hydrolite.sediment_delivery import run_sediment_demo
from hydrolite.ui.components import safe_read_csv, safe_read_excel, show_download
from hydrolite.ui.state import WorkbenchContext

ROOT=Path(__file__).resolve().parents[3]
def render(context: WorkbenchContext)->None:
    st.header("泥沙交付与拦沙")
    st.warning("当前结果不含沟蚀、河岸侵蚀和河床演变时，只能称为坡面泥沙交付估算，不能直接称为完整出口输沙。")
    if st.button("运行 SDR 原创 Demo"): st.success(str(run_sediment_demo()["output_dir"]))
    root=ROOT/"output/sediment_delivery"
    for name in ("sediment_delivery_summary.xlsx","subbasin_sediment_delivery.csv","sediment_delivery_ledger.xlsx"):
        p=root/name
        if p.exists():
            st.subheader(name);st.dataframe(safe_read_excel(p) if p.suffix==".xlsx" else safe_read_csv(p),use_container_width=True);show_download("下载 "+name,p,"application/octet-stream")
