from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.connectors import list_connectors
from hydrolite.ui.state import WorkbenchContext


def render(context: WorkbenchContext) -> None:
    st.header("数据连接器")
    st.caption("GEE、NASA Earthdata、Copernicus CDS、STAC 与本地数据源状态。")
    rows = list_connectors()
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.warning("不会显示或保存凭证；外部下载默认关闭。")
    for row in rows:
        with st.expander(row["display_name"]):
            st.json(row)
            st.info("提供边界、时间范围并确认后才可执行真实检索或下载。")
