from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st


def classify_artifact(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".csv", ".xlsx", ".parquet"}: return "Table"
    if suffix in {".png", ".jpg", ".jpeg", ".svg"}: return "Figure"
    if suffix in {".tif", ".tiff", ".geojson", ".gpkg"}: return "Map"
    if suffix in {".md", ".html", ".docx", ".pdf"}: return "Report"
    if suffix in {".json"}: return "Manifest"
    if suffix in {".yaml", ".yml"}: return "Config"
    return "Dataset"


def render_artifact_list(rows: list[dict]) -> None:
    if not rows:
        st.info("尚无成果。完成场景运行后，成果会按项目、场景、Run 和类型显示在这里。")
        return
    normalized = [{**row, "product_type": row.get("product_type") or classify_artifact(row.get("path", ""))} for row in rows]
    st.dataframe(pd.DataFrame(normalized), use_container_width=True, hide_index=True)
