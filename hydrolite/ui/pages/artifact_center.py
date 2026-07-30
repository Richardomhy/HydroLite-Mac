from __future__ import annotations

from pathlib import Path
import streamlit as st

from hydrolite.artifact_store import create_artifact_bundle, preview_artifact, search_artifacts
from hydrolite.artifact_validation import validate_run_artifacts
from hydrolite.runtime_db import list_run_records
from hydrolite.runtime_paths import get_run_dir


def render(context) -> None:
    st.header("成果中心")
    runs = list_run_records()
    project_filter = st.text_input("项目 ID 筛选")
    run_filter = st.selectbox("Run", [""] + [row["run_id"] for row in runs])
    query = st.text_input("名称或类型搜索")
    rows = search_artifacts(project_filter or None, run_filter or None, query or None)
    types = sorted({row["artifact_type"] for row in rows})
    qualities = sorted({row["quality_status"] for row in rows})
    type_filter = st.selectbox("成果类型", ["全部"] + types)
    quality_filter = st.selectbox("质量状态", ["全部"] + qualities)
    if type_filter != "全部": rows = [row for row in rows if row["artifact_type"] == type_filter]
    if quality_filter != "全部": rows = [row for row in rows if row["quality_status"] == quality_filter]
    st.dataframe(rows, use_container_width=True)
    if run_filter:
        a, b = st.columns(2)
        if a.button("校验 Run 成果"): st.json(validate_run_artifacts(run_filter))
        if b.button("打包 Run 成果"): st.success(create_artifact_bundle(run_filter, get_run_dir(run_filter) / "reports"))
    if rows:
        selected = st.selectbox("预览成果", [row["artifact_id"] for row in rows])
        artifact = next(row for row in rows if row["artifact_id"] == selected)
        st.json(preview_artifact(artifact["path"]))
        path = Path(artifact["path"])
        if path.is_file() and path.stat().st_size < 20 * 1024 * 1024:
            st.download_button("下载成果", path.read_bytes(), file_name=path.name)
