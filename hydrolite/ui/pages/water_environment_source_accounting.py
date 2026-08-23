from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.ui.state import PROJECT_ROOT


DEFAULT_OUTPUT = PROJECT_ROOT / "output/water_environment/m9a"


def read_water_environment_outputs(output_dir: str | Path = DEFAULT_OUTPUT) -> dict:
    root = Path(output_dir)
    manifest_path = root / "reports/m9a_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    return {
        "root": root,
        "manifest": manifest,
        "inventory": root / "inventory/pollution_source_inventory.xlsx",
        "factors": root / "factors/emission_factor_audit.xlsx",
        "ledger": root / "ledger/source_load_ledger.xlsx",
        "coverage": root / "summary/coverage_summary.xlsx",
        "report": root / "reports/m9a_water_environment_source_accounting_report_zh.md",
    }


def _show_table(path: Path, sheet_name: str | int = 0) -> None:
    if not path.is_file(): st.info("尚无该类成果。")
    else: st.dataframe(pd.read_excel(path, sheet_name=sheet_name).head(200), use_container_width=True, hide_index=True)


def render(context) -> None:
    st.header("Water Environment Source Accounting")
    st.caption("Experimental / Foundation · M9A · source_accounting_only")
    st.warning("当前水环境能力仅完成污染源清单和产生/净排放负荷核算，尚未模拟污染物入河输移和河流水质过程。")
    outputs = read_water_environment_outputs()
    if not outputs["manifest"]:
        st.info("尚无 M9A 成果。首次运行需在本地 CLI 显式提供只读真实项目源路径。")
        st.code("python -m hydrolite water-environment inventory --source-root <real-project-source>")
        return
    manifest = outputs["manifest"]
    st.write({
        "source_inventory_validation": manifest.get("source_inventory_validation"),
        "source_load_accounting_validation": manifest.get("source_load_accounting_validation"),
        "water_quality": manifest.get("water_quality"),
        "pollutant_delivery_model_gate": manifest.get("pollutant_delivery_model_gate"),
    })
    tabs = st.tabs(["Sources", "Factors", "Ledger", "Coverage", "Evidence", "Limitations"])
    with tabs[0]: _show_table(outputs["inventory"], "inventory")
    with tabs[1]: _show_table(outputs["factors"], "project_factor_readiness")
    with tabs[2]: _show_table(outputs["ledger"], "source_load_ledger")
    with tabs[3]: _show_table(outputs["coverage"], "coverage")
    with tabs[4]: st.json({"factor_sources": manifest.get("factor_sources"), "evidence_tiers": manifest.get("evidence_tiers"), "data_snapshot_id": manifest.get("data_snapshot_id")})
    with tabs[5]:
        for limitation in manifest.get("limitations", []): st.warning(limitation)
        if outputs["report"].is_file(): st.download_button("下载 M9A 中文报告", outputs["report"].read_bytes(), file_name=outputs["report"].name)
