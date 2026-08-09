from __future__ import annotations

from dataclasses import replace
import streamlit as st

from hydrolite.product_status import get_product_feature_status
from hydrolite.scenario_registry import assess_scenario_readiness, get_scenario, list_scenarios, submit_scenario_run
from hydrolite.ui.components.error_panel import render_error_panel
from hydrolite.ui.components.readiness_panel import render_readiness_panel
from hydrolite.ui.components.scenario_card import render_scenario_card
from hydrolite.ui.components.status_badge import render_status_badge
from hydrolite.ui.components.warning_panel import render_experimental_gate, render_warning_panel
from hydrolite.ui.state import load_app_state, update_app_state


WIZARD_STEPS = ("Goal", "Data", "Readiness", "Configuration", "Review", "Run")


def infer_available_data(context) -> set[str]:
    available: set[str] = set()
    if not context.project_loaded: return available
    text = str(context.project).lower()
    aliases = {
        "rainfall": ("rainfall", "rain"), "subbasins": ("subbasin",), "reaches": ("reach",),
        "observed_streamflow": ("observed_streamflow", "observed_flow"), "dem": ("dem",),
        "soil": ("soil",), "land_cover": ("land_cover",), "project_workspace": ("project_id",),
    }
    for data_id, tokens in aliases.items():
        if any(token in text for token in tokens): available.add(data_id)
    if context.project_loaded: available.add("project_workspace")
    return available


def render(context) -> None:
    state = load_app_state(st.session_state); language = state.language
    st.header("场景中心" if language == "中文" else "Scenario Center")
    st.caption("先选择要解决的业务问题，再检查数据、配置和可信度；底层 Workflow 不会被复制。")
    scenarios = list_scenarios(include_advanced=state.ui_mode == "advanced")
    selected_id = state.current_scenario or scenarios[0]["scenario_id"]
    st.subheader("请选择你的任务")
    for start in range(0, len(scenarios), 3):
        columns = st.columns(3)
        for column, scenario in zip(columns, scenarios[start:start + 3]):
            with column:
                if render_scenario_card(scenario, language):
                    selected_id = scenario["scenario_id"]
                    state = update_app_state(st.session_state, current_scenario=selected_id, last_action="scenario_selected")

    options = [item["scenario_id"] for item in scenarios]
    selected_id = st.selectbox("当前场景", options, index=options.index(selected_id) if selected_id in options else 0)
    update_app_state(st.session_state, current_scenario=selected_id)
    scenario = get_scenario(selected_id)
    st.divider(); st.subheader(f"{scenario.scenario_id} · {scenario.name_zh}")
    render_status_badge(scenario.production_status, language)
    if scenario.production_status == "experimental": render_experimental_gate()
    step = st.segmented_control("场景向导", WIZARD_STEPS, default=WIZARD_STEPS[0]) or WIZARD_STEPS[0]
    available = infer_available_data(context); readiness = assess_scenario_readiness(selected_id, available)
    if step == "Goal":
        st.write(scenario.business_question); st.write(scenario.description)
        st.caption("适合：" + ("、".join(scenario.recommended_for) or "按项目判断"))
        if scenario.not_recommended_for: st.warning("不建议用于：" + "、".join(scenario.not_recommended_for))
    elif step == "Data":
        render_readiness_panel(readiness)
        if scenario.automatic_data_sources: st.caption("可选自动来源：" + ", ".join(scenario.automatic_data_sources))
    elif step == "Readiness":
        render_readiness_panel(readiness)
        for code in readiness.warning_codes: render_warning_panel(code)
    elif step == "Configuration":
        st.json({"scenario_id": selected_id, "workflow_id": scenario.workflow_id, "output_types": scenario.output_types, "advanced_parameters_visible": state.ui_mode == "advanced"})
        if state.ui_mode == "simple": st.info("Simple Mode 只显示运行必需配置；YAML、stage 和模型参数在 Advanced Mode 查看。")
    elif step == "Review":
        st.write("运行前检查")
        for capability in scenario.capabilities:
            status = get_product_feature_status(capability)
            st.write(f"`{capability}` · {status.status} · {status.validation_level}")
            for limitation in status.limitations: st.caption(limitation)
        if scenario.limitations:
            for limitation in scenario.limitations: st.warning(limitation)
    else:
        if not context.project_loaded:
            render_error_panel("user_action", "尚未加载项目。", "先进入项目页面创建或打开项目。")
        else:
            st.info(f"将向现有 Run Manager 提交 `{scenario.workflow_id}`，不会创建第二套运行系统。")
            if st.button("提交运行", type="primary"):
                try:
                    run = submit_scenario_run(context.project_id, selected_id)
                    update_app_state(st.session_state, selected_run=run["run_id"], last_action="run_submitted")
                    st.success(f"Run 已创建：{run['run_id']}")
                except Exception as exc:
                    render_error_panel("environment", str(exc), "确认项目已在运行中心注册。", traceback_text=repr(exc), advanced=state.ui_mode == "advanced")
