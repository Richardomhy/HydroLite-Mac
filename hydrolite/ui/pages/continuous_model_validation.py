from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import streamlit as st

from hydrolite.continuous_validation import DEFAULT_OUTPUT, run_full_continuous_validation
from hydrolite.ui.components import show_download
from hydrolite.ui.state import is_streamlit_cloud


def read_continuous_validation_outputs(output_root: str | Path = DEFAULT_OUTPUT) -> dict[str, object]:
    root=Path(output_root); summary=root/"summary"
    def table(path:Path)->pd.DataFrame:
        try:return pd.read_excel(path)
        except Exception:return pd.DataFrame()
    def payload(path:Path)->dict:
        try:return json.loads(path.read_text(encoding="utf-8"))
        except Exception:return {}
    return {"root":root,"summary":table(summary/"continuous_validation_summary.xlsx"),"manifest":payload(summary/"continuous_validation_manifest.json"),"gate":payload(summary/"water_quality_hydrology_gate.json")}


def render(context) -> None:
    st.header("连续模型验证")
    st.error("水量守恒通过不代表流量模拟通过。水质输移需要可信的地表径流、壤中流、基流和河道过程。")
    outputs=read_continuous_validation_outputs()
    if st.button("运行连续验证", disabled=is_streamlit_cloud()):
        with st.spinner("执行输入、PET、真值恢复与结构诊断..."): run_full_continuous_validation()
        outputs=read_continuous_validation_outputs()
    st.json(outputs["manifest"] or {"status":"not_run"})
    tabs=st.tabs(["输入和单位","PET","完整水量账本","观测流量","合成真值","参数应用","灵敏度","基准模型","分阶段率定","结构诊断","干旱一致性","水环境门禁","报告"])
    sections=["input_audit","pet_audit","balance_audit","input_audit","truth_recovery","parameter_audit","sensitivity","benchmarks","calibration","structure","drought_consistency","summary","summary"]
    for tab,section in zip(tabs,sections):
        with tab:
            folder=outputs["root"]/section
            files=sorted(path for path in folder.glob("*") if path.is_file()) if folder.exists() else []
            if section=="summary": st.json(outputs["gate"] or {"status":"blocked"})
            st.dataframe(pd.DataFrame([{"file":path.name,"bytes":path.stat().st_size} for path in files]),use_container_width=True)
            for path in files:
                if path.suffix==".png": st.image(str(path),use_container_width=True)
            for path in files:
                if path.suffix in {".xlsx",".md",".json",".csv"}: show_download(f"下载 {path.name}",path,"application/octet-stream")
