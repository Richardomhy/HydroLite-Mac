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

M8B_OUTPUTS = {
    "流域与拓扑": "m8b/basin/basin_summary.xlsx",
    "参数来源": "m8b/inputs/parameter_provenance.xlsx",
    "事件就绪度": "m8b/events/event_readiness.xlsx",
    "真实运行验证": "m8b/validation/validation_summary.xlsx",
    "情景对比": "m8b/scenarios/scenario_comparison.xlsx",
    "湿天气水质诊断": "m8b/water_quality/wet_weather_event_diagnostic.xlsx",
    "产品摩擦闭环": "m8b/product/friction_closure.xlsx",
    "版本对比": "m8b/delivery/version_comparison.xlsx",
}


def load_real_project_baseline(output_dir: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(output_dir)
    mappings = (M8B_OUTPUTS, OUTPUTS) if (root / "m8b").is_dir() else (OUTPUTS,)
    return {
        name: pd.read_excel(root / relative)
        for mapping in mappings
        for name, relative in mapping.items()
        if (root / relative).is_file()
    }


def load_real_project_manifest(output_dir: str | Path) -> dict:
    root = Path(output_dir)
    for path in (root / "m8b/reports/m8b_manifest.json", root / "reports/m8a_real_project_manifest.json"):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                return {}
    return {}


def build_real_project_summary(manifest: dict) -> dict[str, str]:
    version = manifest.get("project_version") or manifest.get("project_version_id") or "unavailable"
    if isinstance(version, dict):
        version = version.get("project_version_id") or version.get("id") or "unavailable"
    run_ids = manifest.get("actual_hydrolite_run_ids") or manifest.get("actual_run_ids") or manifest.get("run_ids") or manifest.get("run_id") or []
    if not isinstance(run_ids, list):
        run_ids = [run_ids]
    scientific = manifest.get("scientific_status") or manifest.get("scientific_validation_level") or manifest.get("validation_status") or "not_tested"
    scenario = manifest.get("scenario_type") or manifest.get("scenario_analysis_type") or "unavailable"
    delivery = manifest.get("delivery_review_status") or manifest.get("review_status") or "unavailable"
    return {
        "Project Version": str(version),
        "HydroLite Real Run": ", ".join(map(str, run_ids)) or "unavailable",
        "Scientific Validation": str(scientific),
        "Scenario": str(scenario),
        "Delivery": str(delivery),
    }


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
    manifest = load_real_project_manifest(root)
    if (root / "m8b/reports/m8b_manifest.json").is_file():
        summary = build_real_project_summary(manifest)
        scientific = summary["Scientific Validation"]
        rows = (
            ("Projects", "passed" if context.project_loaded else "blocked"),
            ("Scenario", "passed" if "情景对比" in tables else "blocked"),
            ("Data", "passed" if {"流域与拓扑", "参数来源"} <= tables.keys() else "blocked"),
            ("Readiness", "passed" if "事件就绪度" in tables else "warning"),
            ("Run", "passed" if summary["HydroLite Real Run"] != "unavailable" else "blocked"),
            ("Results", "passed" if scientific in {"real_data_tested", "independently_validated", "production_ready"} else "warning"),
            ("Delivery", "passed" if manifest.get("integrity_status") == "passed" and summary["Delivery"] in {"reviewed", "approved_for_delivery"} else "blocked"),
        )
        return pd.DataFrame([{"环节": name, "状态": status} for name, status in rows])
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
    st.header("真实项目基线与验证")
    root = find_real_project_baseline(context)
    tables = load_real_project_baseline(root)
    if not tables:
        st.info("尚无真实项目基线输出。本地使用 `python -m hydrolite real-project audit <source_root>` 生成；云端不读取用户本地资料。")
        return
    manifest = load_real_project_manifest(root)
    m8b = (root / "m8b/reports/m8b_manifest.json").is_file()
    st.caption("M8B 真实模型闭环：运行、科学验证与交付状态相互独立。" if m8b else "M8A 只读审计：真实证据、能力状态和交付状态相互独立。")
    if m8b:
        summary = build_real_project_summary(manifest)
        for column, (label, value) in zip(st.columns(5), summary.items()):
            column.metric(label, value)
        for warning in manifest.get("warnings", []):
            st.warning(str(warning))
        for limitation in manifest.get("limitations", []):
            st.caption(f"Limitation: {limitation}")
    closure = build_ui_closure(context, root, tables)
    st.subheader("UI 闭环")
    st.dataframe(closure, use_container_width=True, hide_index=True)
    for title, frame in tables.items():
        with st.expander(title, expanded=title in {"能力就绪度", "真实验证"}):
            st.dataframe(frame.head(200), use_container_width=True, hide_index=True)
    report = root / ("m8b/reports/m8b_real_model_validation_report_zh.md" if m8b else "reports/m8a_real_project_baseline_report_zh.md")
    if report.is_file():
        st.subheader("真实项目报告")
        st.markdown(report.read_text(encoding="utf-8"))
