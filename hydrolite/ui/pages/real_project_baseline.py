from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.ui.state import WorkbenchContext


OUTPUTS = {
    "数据清单": "inventory/real_project_data_inventory.xlsx",
    "数据质量": "data_quality/dataset_quality_summary.xlsx",
    "字段映射": "data_quality/field_mapping_audit.xlsx",
    "空间审计": "data_quality/spatial_mapping_audit.xlsx",
    "能力就绪度": "readiness/capability_readiness.xlsx",
    "真实验证": "validation/real_validation_summary.xlsx",
    "产品摩擦": "product/product_friction_backlog.xlsx",
    "商业就绪度": "product/commercial_readiness.xlsx",
}


def load_real_project_baseline(output_dir: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(output_dir)
    return {name: pd.read_excel(root / relative) for name, relative in OUTPUTS.items() if (root / relative).is_file()}


def find_real_project_baseline(context: WorkbenchContext) -> Path:
    pointer = context.project_dir / "reports" / "real_project_baseline_pointer.json"
    if pointer.is_file():
        try:
            candidate = Path(json.loads(pointer.read_text(encoding="utf-8"))["output_dir"])
            if candidate.is_dir():
                return candidate
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    candidates = (
        context.project_dir / "outputs" / "real_project_validation",
        Path(__file__).resolve().parents[3] / "output" / "real_project_validation",
    )
    return next((path for path in candidates if path.is_dir()), candidates[0])


def build_ui_closure(context: WorkbenchContext, root: Path, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    manifest_path = root / "reports" / "m8a_real_project_manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    rows = (
        ("Projects", "passed" if context.project_loaded else "blocked"),
        ("Scenario", "warning"),
        ("Data", "passed" if "数据清单" in tables else "blocked"),
        ("Readiness", "passed" if "能力就绪度" in tables else "blocked"),
        ("Run", "warning" if "真实验证" in tables else "blocked"),
        ("Results", "passed" if tables else "blocked"),
        ("Delivery", "passed" if manifest.get("integrity_status") == "passed" and manifest.get("delivery_review_status") == "reviewed" else "blocked"),
    )
    return pd.DataFrame([{"\u73af\u8282": name, "\u72b6\u6001": status} for name, status in rows])


def render(context: WorkbenchContext) -> None:
    st.header("真实项目基线")
    st.caption("M8A 只读审计：真实证据、能力状态和交付状态相互独立。")
    root = find_real_project_baseline(context)
    tables = load_real_project_baseline(root)
    if not tables:
        st.info("尚无真实项目基线输出。本地使用 `python -m hydrolite real-project audit <source_root>` 生成；云端不读取用户本地资料。")
        return
    closure = build_ui_closure(context, root, tables)
    st.subheader("UI 闭环")
    st.dataframe(closure, use_container_width=True, hide_index=True)
    for title, frame in tables.items():
        with st.expander(title, expanded=title in {"能力就绪度", "真实验证"}):
            st.dataframe(frame.head(200), use_container_width=True, hide_index=True)
    report = root / "reports" / "m8a_real_project_baseline_report_zh.md"
    if report.is_file():
        st.subheader("基线报告")
        st.markdown(report.read_text(encoding="utf-8"))
