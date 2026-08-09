from __future__ import annotations

import streamlit as st


def render_metric_card(label: str, value, help_text: str | None = None) -> None:
    st.caption(label, help=help_text)
    st.markdown(f"**{'—' if value is None else value}**")
