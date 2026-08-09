from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import streamlit as st

from hydrolite.ui.components.warning_panel import render_experimental_gate, render_warning_panel
from hydrolite.ui.state import PROJECT_ROOT


ROOT = PROJECT_ROOT / "output/method_inspiration/water_quality"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists(): return pd.DataFrame()
    try: return pd.read_csv(path, low_memory=False) if path.suffix == ".csv" else pd.read_excel(path)
    except Exception: return pd.DataFrame()


def render(context) -> None:
    st.header("Water Quality Method Lab")
    render_experimental_gate()
    st.error("正式 water_quality 主能力仍为 planned；本页不是 Production Water Quality Model。")
    manifest_path = ROOT / "reports/water_quality_method_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    tabs = st.tabs(["Data QC", "Station Network", "Concentration", "Load", "Forecast", "Ablation", "Diagnostics", "Limitations"])
    candidates = {
        "Data QC": ROOT / "data_quality/observation_qc.xlsx",
        "Station Network": ROOT / "data_quality/station_mapping.xlsx",
        "Concentration": ROOT / "forecast/station_predictions.csv",
        "Load": ROOT / "loads/concentration_load.csv",
        "Forecast": ROOT / "forecast/horizon_metrics.xlsx",
        "Ablation": ROOT / "benchmark/feature_ablation.xlsx",
        "Diagnostics": ROOT / "diagnostics/threshold_diagnostics.xlsx",
    }
    for tab, name in zip(tabs[:-1], candidates):
        with tab:
            frame = _read(candidates[name])
            if frame.empty: st.info("尚无该类实验成果；可运行已有 water-quality-lab Demo。")
            else: st.dataframe(frame.head(200), use_container_width=True, hide_index=True)
    with tabs[-1]:
        st.write("Synthetic evidence：Hydrology 12/16，Graph 13/16，Gamma 1/16，Trend 0/16；overall mixed。")
        st.write("Real-data evidence：not tested。")
        st.warning("Trend value-added 未得到证明，不能默认推荐。")
        if manifest: st.json({key: manifest.get(key) for key in ("validation_level", "water_quality_method_value_added", "real_data_value_added")})
        render_warning_panel("REAL_DATA_VALIDATION_MISSING")
