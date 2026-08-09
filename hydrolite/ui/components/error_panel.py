from __future__ import annotations

import streamlit as st


ERROR_TYPES = {"user_action": "User Action Required", "dependency": "Dependency Missing", "data": "Data Invalid", "model": "Model Blocked", "environment": "Environment Error", "internal": "Internal Error"}


def render_error_panel(error_type: str, message: str, action: str = "", traceback_text: str = "", advanced: bool = False) -> None:
    title = ERROR_TYPES.get(error_type, ERROR_TYPES["internal"])
    st.error(f"{title}: {message}")
    if action: st.info(f"Recommended action: {action}")
    if advanced and traceback_text:
        with st.expander("Technical details"): st.code(traceback_text)
