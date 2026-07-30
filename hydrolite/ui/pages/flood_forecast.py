from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from hydrolite.flood_forecast import (
    DEFAULT_OUTPUT,
    assess_flood_forecast_readiness,
    create_flood_forecast_config,
    export_flood_forecast_bundle,
    run_flood_forecast_demo,
    validate_flood_forecast_outputs,
)
from hydrolite.lstm_forecast import detect_torch_environment, run_lstm_synthetic_smoke_test
from hydrolite.ml_forecast import assess_ml_data_readiness, run_ml_synthetic_demo
from hydrolite.ui.components import show_download
from hydrolite.ui.state import PROJECT_ROOT, WorkbenchContext, is_streamlit_cloud


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def render(context: WorkbenchContext) -> None:
    root = Path(DEFAULT_OUTPUT)
    st.header("洪水预测")
    st.warning("当前为情景集合与历史回放 MVP。真实业务预测需要实时降雨预报、连续水文状态、多事件独立验证、真实水库曲线和运行监控。")
    tabs = st.tabs(["预测就绪度", "降雨输入", "物理模型", "机器学习", "LSTM", "水库调蓄", "集合与不确定性", "阈值", "报告与下载"])
    project = context.project_dir if context.project_loaded else PROJECT_ROOT / "projects" / "qgis_workflow_project"

    with tabs[0]:
        if st.button("运行诊断"):
            st.json(assess_flood_forecast_readiness(project))
        readiness = _read_json(root / "forecast_readiness.json")
        st.json(readiness or {"status": "not_run"})
        st.caption("预测等级最高为 synthetic_demo；HEC-HMS Reservoir 保持 blocked_gate。")
        if st.button("创建配置"):
            path = create_flood_forecast_config(project, root / "forecast_config.yaml")
            st.success(f"配置已生成：`{path}`")

    with tabs[1]:
        st.write("输入单位：毫米；默认 60 分钟时段。scenario 不会标记为正式 forecast。")
        if (root / "rainfall" / "rainfall_member_summary.xlsx").exists():
            st.dataframe(pd.read_excel(root / "rainfall" / "rainfall_member_summary.xlsx"), use_container_width=True)
        st.button("导入降雨", disabled=True, help="本 MVP 使用标准 CSV 协议；请通过配置文件导入。")
        if st.button("生成情景集合"):
            run_flood_forecast_demo(root)
            st.success("已生成 6 个演示降雨情景。")

    with tabs[2]:
        st.caption("HydroLite 全成员运行；本地 HEC-HMS 为可选，云端不启动。失败成员保留原因。")
        c1, c2 = st.columns(2)
        if c1.button("运行 HydroLite"):
            run_flood_forecast_demo(root); st.success("HydroLite 情景集合完成。")
        c2.button("运行 HEC-HMS", disabled=is_streamlit_cloud(), help="云端禁用；本地成员 DSS 门禁未启用时会安全跳过。")
        if (root / "physics" / "member_run_summary.xlsx").exists():
            st.dataframe(pd.read_excel(root / "physics" / "member_run_summary.xlsx"), use_container_width=True)

    with tabs[3]:
        if st.button("检查 ML 数据"):
            st.json(assess_ml_data_readiness(project))
        if st.button("运行 ML Demo"):
            result = run_ml_synthetic_demo(PROJECT_ROOT / "data_demo" / "flood_forecast" / "demo_ml_timeseries.csv", root / "ml")
            st.json(result)
        if (root / "ml" / "ml_model_summary.xlsx").exists():
            st.dataframe(pd.read_excel(root / "ml" / "ml_model_summary.xlsx"), use_container_width=True)

    with tabs[4]:
        st.json(detect_torch_environment())
        if st.button("检查 LSTM"):
            st.info("真实项目数据门禁：insufficient_data。")
        if st.button("运行 LSTM Smoke Test", disabled=is_streamlit_cloud()):
            st.json(run_lstm_synthetic_smoke_test(root / "lstm"))
        st.caption("框架验证不等于真实模型训练；云端不训练 LSTM。")

    with tabs[5]:
        if st.button("运行水库联算"):
            run_flood_forecast_demo(root); st.success("HydroLite synthetic-demo 水库成员完成；HEC-HMS Reservoir 已跳过。")
        if (root / "ensemble" / "reservoir_stage_distribution.xlsx").exists():
            st.dataframe(pd.read_excel(root / "ensemble" / "reservoir_stage_distribution.xlsx"), use_container_width=True)
        st.warning("库水位来自 synthetic_demo 曲线，不用于真实调度建议。")

    with tabs[6]:
        if st.button("汇总集合"):
            run_flood_forecast_demo(root); st.success("集合分位数已更新。")
        if (root / "ensemble" / "peak_distribution.xlsx").exists():
            peak = pd.read_excel(root / "ensemble" / "peak_distribution.xlsx")
            st.dataframe(peak, use_container_width=True)
            row = peak.iloc[0]
            st.metric("峰值 p50", f"{row['p50']:.2f} m3/s")
        for name in ("outlet_flow_ensemble.png", "outlet_flow_quantiles.png", "peak_distribution.png"):
            path = root / "charts" / name
            if path.exists():
                st.image(str(path), use_container_width=True)

    with tabs[7]:
        if st.button("计算阈值"):
            run_flood_forecast_demo(root); st.success("诊断阈值已计算。")
        if (root / "ensemble" / "threshold_exceedance.xlsx").exists():
            st.dataframe(pd.read_excel(root / "ensemble" / "threshold_exceedance.xlsx"), use_container_width=True)
        st.caption("成员超限比例是 scenario_member_exceedance_fraction，不是法定预警概率。")

    with tabs[8]:
        if st.button("运行完整 Demo"):
            with st.spinner("运行轻量情景集合..."):
                result = run_flood_forecast_demo(root)
            st.success(result["status"])
        c1, c2 = st.columns(2)
        if c1.button("生成报告"):
            st.success("完整 Demo 会自动生成中英文报告。")
        if c2.button("生成 bundle"):
            st.success(f"已生成：`{export_flood_forecast_bundle(root)}`")
        st.json(validate_flood_forecast_outputs(root))
        for label, path, mime in [
            ("下载中文报告", root / "reports" / "flood_forecast_report_zh.md", "text/markdown"),
            ("下载英文报告", root / "reports" / "flood_forecast_report_en.md", "text/markdown"),
            ("下载集合 CSV", root / "ensemble" / "ensemble_timeseries.csv", "text/csv"),
            ("下载预测 bundle", root / "flood_forecast_bundle.zip", "application/zip"),
        ]:
            show_download(label, path, mime)
