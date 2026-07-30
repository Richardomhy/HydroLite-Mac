import streamlit as st
from hydrolite.watershed_accounting import ROOT, build_watershed_accounting
from hydrolite.ui.components import safe_read_excel, show_download
from hydrolite.ui.state import WorkbenchContext
def render(context: WorkbenchContext) -> None:
    st.header("流域综合核算")
    st.warning("当前核算状态默认 partial；缺失项保持空值，不按零处理。")
    output=ROOT/"output/watershed_accounting"
    if st.button("构建核算台账"): st.success(build_watershed_accounting(context.project_dir)["accounting_status"])
    for name in ("water_accounting_ledger.xlsx","soil_sediment_accounting_ledger.xlsx","accounting_completeness_matrix.xlsx"):
        p=output/name
        if p.exists(): st.subheader(name);st.dataframe(safe_read_excel(p),use_container_width=True);show_download("下载 "+name,p,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
