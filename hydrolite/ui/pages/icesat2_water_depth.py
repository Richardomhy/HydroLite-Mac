from pathlib import Path
import streamlit as st
from hydrolite.icesat2 import DEFAULT_OUTPUT, detect_earthdata_access, detect_icesat2_dependencies, run_icesat2_demo
from hydrolite.ui.components import safe_read_csv, safe_read_excel, show_download
from hydrolite.ui.state import WorkbenchContext
def render(context: WorkbenchContext) -> None:
    st.header("ICESat-2 水深")
    st.warning("ICESat-2 是沿轨观测；连续水深和库容必须结合 DEM、岸线、测深或现场数据复核。")
    st.json({"dependencies":detect_icesat2_dependencies(),"earthdata":detect_earthdata_access()})
    if st.button("运行 Demo"): st.success(str(run_icesat2_demo()["report"]))
    for name in ("water_surface_points.csv","bathymetry_points.csv","depth_profiles.csv","stage_area_volume.csv"):
        p=DEFAULT_OUTPUT/name
        if p.exists(): st.subheader(name);st.dataframe(safe_read_csv(p),use_container_width=True);show_download("下载 "+name,p,"text/csv")
    p=DEFAULT_OUTPUT/"track_coverage.xlsx"
    if p.exists(): st.dataframe(safe_read_excel(p),use_container_width=True)
