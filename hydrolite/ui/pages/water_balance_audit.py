from pathlib import Path
import streamlit as st
from hydrolite.water_balance_audit import reconcile_hydrologic_water_balance, write_water_balance_audit
from hydrolite.ui.components import safe_read_excel, show_download
from hydrolite.ui.state import WorkbenchContext
ROOT=Path(__file__).resolve().parents[3]
def render(context:WorkbenchContext)->None:
    st.header("水量平衡审计")
    st.warning("洪水预测在水量平衡与 HEC-HMS Reservoir 两个门禁完成前保持禁用。完整过程线用于水量核算，比较窗口仅用于跨模型对比。")
    if st.button("审计当前项目"):
        result=reconcile_hydrologic_water_balance(context.project_dir);st.success(str(write_water_balance_audit(ROOT/"output/water_balance_audit",result)["report"]))
    root=ROOT/"output/water_balance_audit";book=root/"hydrologic_balance_ledger.xlsx"
    if book.exists():
        for sheet in ("subbasin","reach","outlet","tail"):
            st.subheader(sheet);st.dataframe(safe_read_excel(book,sheet),use_container_width=True)
        show_download("下载水量平衡账本",book,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
