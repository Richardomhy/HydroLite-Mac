from __future__ import annotations

import streamlit as st

from hydrolite.ui.components.status_badge import render_status_badge


def render_scenario_card(scenario: dict, language: str = "中文") -> bool:
    name = scenario["name_zh"] if language == "中文" else scenario["name_en"]
    with st.container(border=True):
        st.subheader(f"{scenario['scenario_id']} · {name}")
        st.write(scenario["business_question"])
        render_status_badge(scenario["production_status"], language)
        required = ", ".join(scenario["required_data"]) or "无需预先上传"
        outputs = ", ".join(scenario["output_types"])
        st.caption(f"需要：{required}")
        st.caption(f"预计输出：{outputs}")
        return st.button("开始" if language == "中文" else "Start", key=f"start_{scenario['scenario_id']}", use_container_width=True)
