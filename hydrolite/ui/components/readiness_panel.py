from __future__ import annotations

import pandas as pd
import streamlit as st


READINESS_ACTIONS = {
    "missing": "Manual Action Required",
    "invalid": "Manual Action Required",
    "needs_mapping": "Auto Fix Available / Manual Review",
    "needs_unit_fix": "Auto Fix Available / Manual Review",
    "needs_crs_fix": "Auto Fix Available / Manual Review",
    "available": "No action required",
    "optional_missing": "Optional",
}


def readiness_rows(readiness) -> list[dict[str, str]]:
    rows = []
    for requirement_type, items in (("Required Data", readiness.required), ("Optional Data", readiness.optional)):
        for item in items:
            status = item["status"]
            rows.append({"type": requirement_type, "data_id": item["data_id"], "status": status, "action": READINESS_ACTIONS.get(status, "Manual Action Required")})
    return rows


def render_readiness_panel(readiness) -> None:
    st.subheader("数据就绪度")
    rows = readiness_rows(readiness)
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else: st.info("此场景没有必需的用户数据，可直接查看配置。")
    if readiness.next_recommended_action: st.info(f"下一步建议：{readiness.next_recommended_action}")
