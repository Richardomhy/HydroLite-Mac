import streamlit as st
from hydrolite.rusle import ROOT, run_rusle
from hydrolite.ui.components import safe_read_excel, show_download
from hydrolite.ui.state import WorkbenchContext
def render(context: WorkbenchContext) -> None:
    st.header("RUSLE 土壤侵蚀")
    st.warning("RUSLE 是长期平均片蚀和细沟侵蚀模型，不直接等于入河泥沙或单场洪水侵蚀。")
    output=ROOT/"output/rusle"
    if st.button("运行合成 RUSLE Demo"): st.success(str(run_rusle(ROOT/"data_demo/rusle/demo_rusle_config.yaml",output)["output_dir"]))
    for name in ("factor_summary.xlsx","factor_quality.xlsx","subbasin_soil_loss.xlsx","subbasin_conservation.xlsx"):
        p=output/name
        if p.exists(): st.subheader(name);st.dataframe(safe_read_excel(p),use_container_width=True);show_download("下载 "+name,p,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
