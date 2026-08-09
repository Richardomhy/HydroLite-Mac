from __future__ import annotations

import streamlit as st


WARNING_CATALOG = {
    "REAL_DATA_VALIDATION_MISSING": ("缺少真实数据独立验证", "结果只能视为实验或框架证据。", "补充独立真实观测并重新验证。"),
    "GEE_COMPUTE_AUTH_UNAVAILABLE": ("GEE 计算认证不可用", "离线目录仍可查询，但不能执行计算或导出。", "本地配置 Earth Engine 认证。"),
    "XAI_IMPORTANCE_UNSTABLE": ("XAI 重要性不稳定", "不同模型或空间块的重要性变化较大。", "不要把单次重要性作为业务因果结论。"),
    "LONG_HORIZON_LOW_SKILL": ("长提前期技巧较低", "累计误差可能随 horizon 增大。", "按 horizon 审阅独立指标。"),
    "DATA_MAPPING_LOW_CONFIDENCE": ("数据映射置信度低", "字段或站点关系可能影响结果。", "人工核验映射。"),
    "LOW_CONFIDENCE_MAPPING": ("数据映射置信度低", "字段或站点关系可能影响结果。", "人工核验映射。"),
}
EXPERIMENTAL_NOTICE = "实验功能：当前能力已通过软件和合成数据验证，但尚未完成真实项目独立验证。结果不能直接用于正式工程或管理决策。"


def warning_payload(code: str) -> dict[str, str]:
    meaning, impact, action = WARNING_CATALOG.get(code, (code, "请审阅详细信息。", "检查数据、环境和限制。"))
    return {"warning_code": code, "meaning": meaning, "impact": impact, "recommended_action": action}


def render_warning_panel(code: str) -> None:
    payload = warning_payload(code)
    st.warning(f"{payload['meaning']}\n\n影响：{payload['impact']}\n\n建议：{payload['recommended_action']}")


def render_experimental_gate() -> None:
    st.warning(EXPERIMENTAL_NOTICE)
