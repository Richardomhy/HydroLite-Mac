from __future__ import annotations

import streamlit as st


STATUS_LABELS = {
    "production_ready": ("可用于生产流程", "Ready"),
    "ready_with_warnings": ("可用但有警告", "Ready with warnings"),
    "experimental": ("实验功能", "Experimental"),
    "planned": ("规划中", "Planned"),
    "unavailable": ("当前不可用", "Unavailable"),
}


def status_text(status: str, language: str = "中文") -> str:
    labels = STATUS_LABELS.get(status, (status, status))
    return labels[0] if language == "中文" else labels[1]


def render_status_badge(status: str, language: str = "中文") -> None:
    label = status_text(status, language)
    if status == "production_ready": st.success(label)
    elif status == "ready_with_warnings": st.warning(label)
    elif status == "experimental": st.warning(f"{label} · 真实项目独立验证未完成")
    elif status == "planned": st.info(label)
    else: st.error(label)
