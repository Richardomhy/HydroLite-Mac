from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import streamlit as st

from hydrolite.continuous_hydrology import run_continuous_config
from hydrolite.drought_lstm import assess_drought_lstm_readiness, run_drought_lstm_synthetic_smoke_test
from hydrolite.drought_ml import assess_drought_ml_readiness, run_drought_ml_synthetic_demo
from hydrolite.drought_workflow import (
    DEFAULT_ROOT, DEMO_PROJECT, assess_drought_readiness, create_drought_demo_scenarios,
    export_drought_model_bundle, run_drought_assimilation_workflow,
    run_drought_events_workflow, run_drought_forecast_demo,
    run_drought_indices_workflow, run_drought_monitoring_workflow,
    run_drought_uncertainty_workflow, validate_drought_model, write_drought_summary,
)
from hydrolite.ui.components import show_download
from hydrolite.ui.state import is_streamlit_cloud
from hydrolite.drought_consistency import classify_component_availability, calculate_composite_weight_audit


def read_drought_outputs(output_root: str | Path = DEFAULT_ROOT) -> dict[str, object]:
    root = Path(output_root)
    def csv(relative: str) -> pd.DataFrame:
        path = root / relative
        try: return pd.read_csv(path)
        except Exception: return pd.DataFrame()
    def xlsx(relative: str, sheet=0) -> pd.DataFrame:
        path = root / relative
        try: return pd.read_excel(path, sheet_name=sheet)
        except Exception: return pd.DataFrame()
    def payload(relative: str) -> dict:
        try: return json.loads((root / relative).read_text(encoding="utf-8"))
        except Exception: return {}
    return {
        "manifest": payload("continuous/continuous_model_manifest.json"),
        "daily_balance": csv("continuous/daily_water_balance.csv"),
        "states": csv("continuous/daily_states.csv"),
        "indices": csv("indices/drought_indices_monthly.csv"),
        "events": xlsx("indices/drought_event_catalog.xlsx"),
        "monitoring": payload("monitoring/current_drought_status.json"),
        "forecast": payload("forecast/drought_forecast_manifest.json"),
        "forecast_quantiles": csv("forecast/drought_index_quantiles.csv"),
        "assimilation": csv("assimilation/assimilation_adjustments.csv"),
    }


def _chart(root: Path, relative: str) -> None:
    path = root / relative
    if path.exists():
        st.image(str(path), use_container_width=True)


def render(context) -> None:
    root = Path(DEFAULT_ROOT)
    project = DEMO_PROJECT
    st.header("干旱分析与预测")
    st.warning("当前软件诊断等级不等于当地法定干旱预警标准。真实预测需要长期连续观测和经验证的气象预报输入。")
    st.caption("事件水文用于单场洪水；本页的日尺度连续模型保留土壤水、地下水、河道和可选水库的跨日状态。")
    tabs = st.tabs([
        "数据就绪度", "连续水文", "蒸散发", "土壤水", "地下水与基流", "水库状态",
        "干旱指标", "历史事件", "当前状态", "情景集合", "预测", "状态同化", "机器学习", "报告与下载",
    ])
    outputs = read_drought_outputs(root)
    with tabs[0]:
        st.json(assess_drought_readiness(project))
        st.caption("Demo 为 20 年 synthetic_demo；GEE/CDS/Earthdata 连接器默认 dry-run，未认证不会阻断本页。")
        st.info("Streamlit Cloud 只运行轻量 Demo，集合最多 10 个成员，不下载大型 NetCDF/HDF5，也不训练 LSTM。")
    with tabs[1]:
        if st.button("运行连续模拟", disabled=is_streamlit_cloud()):
            with st.spinner("推进 20 年日尺度状态..."):
                result = run_continuous_config(project / "continuous_model_config.yaml")
            st.success(f"水量门禁：{result['validation']['status']}")
        manifest = outputs["manifest"]
        cols = st.columns(4)
        cols[0].metric("起止", f"{manifest.get('start_date','-')} / {manifest.get('end_date','-')}")
        cols[1].metric("记录日数", manifest.get("record_days", 0))
        cols[2].metric("PET 方法", manifest.get("pet_method", "-"))
        cols[3].metric("水量门禁", manifest.get("water_balance", {}).get("status", "not_run"))
        st.dataframe(outputs["daily_balance"].head(200), use_container_width=True)
        _chart(root, "continuous/charts/annual_water_balance.png")
    with tabs[2]:
        st.json({key: outputs["manifest"].get(key) for key in ("pet_method", "synthetic_demo")})
        _chart(root, "continuous/charts/precipitation_pet_timeseries.png")
        st.caption("优先用户合格 PET；输入完整才使用 FAO56；温度和纬度可使用 Hargreaves；气候态仅供 synthetic Demo。")
    with tabs[3]:
        st.dataframe(outputs["states"].filter(regex="date|subbasin|soil").head(200), use_container_width=True)
        _chart(root, "continuous/charts/soil_moisture_timeseries.png")
    with tabs[4]:
        st.dataframe(outputs["states"].filter(regex="date|subbasin|groundwater").head(200), use_container_width=True)
        _chart(root, "continuous/charts/groundwater_storage_timeseries.png")
        _chart(root, "continuous/charts/runoff_baseflow_timeseries.png")
        st.caption("模型地下水储量是概念状态，不等于实测地下水位。")
    with tabs[5]:
        st.warning("Demo 连续配置为 `no_reservoir`；水库干旱状态为 unavailable，不显示为 normal。真实水库需用户提供 release/曲线/规则，不自动推断调度。")
        if "reservoir_storage_m3" in outputs["states"]:
            st.dataframe(outputs["states"][["date", "subbasin_id", "reservoir_storage_m3"]].head(200), use_container_width=True)
    with tabs[6]:
        if st.button("计算干旱指标"):
            run_drought_indices_workflow(project); st.success("SPI/SPEI/SSI 与百分位已更新。")
        st.dataframe(outputs["indices"].head(200), use_container_width=True)
        for name in ("spi_timeseries.png", "spei_timeseries.png", "ssi_timeseries.png", "composite_drought_index.png"):
            _chart(root, f"indices/{name}")
    with tabs[7]:
        if st.button("识别历史事件"):
            run_drought_events_workflow(project); st.success("历史事件目录已更新。")
        st.dataframe(outputs["events"], use_container_width=True)
        _chart(root, "indices/drought_event_timeline.png")
        _chart(root, "indices/drought_severity_duration.png")
    with tabs[8]:
        if st.button("评估当前状态"):
            run_drought_monitoring_workflow(project); st.success("当前状态已更新。")
        st.json(outputs["monitoring"] or {"status":"not_run"})
        availability = classify_component_availability(root)
        st.dataframe(calculate_composite_weight_audit(availability), use_container_width=True)
        st.caption("缺失分量不参与综合指数；模型地下水状态是 model_generated，不是实测地下水。")
    with tabs[9]:
        if st.button("生成情景集合"):
            scenarios=create_drought_demo_scenarios(project); st.success(f"已生成 {scenarios.member_id.nunique()} 个成员。")
        st.caption("baseline、降雨 80%/60%、温度 +1/+2°C、雨季偏移和干历史类比均为情景，不是发布的气象预报。")
    with tabs[10]:
        if st.button("运行干旱预测 Demo", disabled=is_streamlit_cloud()):
            result=run_drought_forecast_demo(project);st.success(f"{result['successful_members']}/{result['member_count']} 个成员成功")
        st.json(outputs["forecast"] or {"status":"not_run"})
        st.dataframe(outputs["forecast_quantiles"], use_container_width=True)
        _chart(root, "forecast/forecast_index_quantiles.png")
        _chart(root, "forecast/drought_class_member_fraction.png")
        _chart(root, "forecast/onset_recovery_distribution.png")
    with tabs[11]:
        if st.button("运行状态同化"):
            result=run_drought_assimilation_workflow(project);st.success(f"记录 {len(result['adjustments'])} 条显式 adjustment")
        st.dataframe(outputs["assimilation"], use_container_width=True)
        _chart(root, "assimilation/open_loop_vs_assimilated_state.png")
    with tabs[12]:
        st.json(assess_drought_ml_readiness(project / "daily_meteorology.csv"))
        if st.button("运行 ML Demo"):
            st.json(run_drought_ml_synthetic_demo(root / "ml"))
        st.json(assess_drought_lstm_readiness(project / "daily_meteorology.csv"))
        if st.button("运行 LSTM Smoke", disabled=is_streamlit_cloud()):
            st.json(run_drought_lstm_synthetic_smoke_test(root / "lstm"))
        st.caption("不自动安装 PyTorch；合成 Smoke 不等于真实训练或预测。")
    with tabs[13]:
        a,b,c=st.columns(3)
        if a.button("生成报告"): st.json({key:str(value) for key,value in write_drought_summary(root).items()})
        if b.button("生成 Bundle"): st.success(export_drought_model_bundle(root))
        if c.button("校验成果"): st.json(validate_drought_model(root))
        for label,relative,mime in (
            ("连续模型中文报告","continuous/continuous_model_report_zh.md","text/markdown"),
            ("干旱指标中文报告","indices/drought_index_report_zh.md","text/markdown"),
            ("当前干旱报告","monitoring/current_drought_report_zh.md","text/markdown"),
            ("预测中文报告","forecast/drought_forecast_report_zh.md","text/markdown"),
            ("综合报告","summary/drought_model_report_zh.md","text/markdown"),
            ("下载 Bundle","summary/drought_model_bundle.zip","application/zip"),
        ):
            show_download(label,root/relative,mime)
