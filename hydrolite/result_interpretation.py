"""Deterministic result interpretation without invented scientific claims."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class ResultInterpretation:
    headline: str
    summary: str
    key_findings: tuple[str, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    recommended_next_steps: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def interpret_result(
    metrics: dict[str, Any] | None,
    *, validation_status: str,
    readiness: str,
    limitations: Iterable[str] = (),
    result_type: str = "analysis",
) -> ResultInterpretation:
    values = dict(metrics or {}); limits = tuple(str(item) for item in limitations)
    findings = tuple(f"{key}: {value}" for key, value in values.items() if value is not None)
    warnings: list[str] = []
    if validation_status in {"synthetic_demo", "not_tested", "framework_ready"}:
        warnings.append("REAL_DATA_VALIDATION_MISSING")
    if readiness not in {"ready", "ready_with_warnings"}:
        warnings.append("DATA_READINESS_INCOMPLETE")
    headline = "结果可供审阅" if findings else "尚无可解释结果"
    summary = f"{result_type} 结果包含 {len(findings)} 项已提供指标；未提供的科学结论不会被自动推断。"
    next_steps = []
    if "REAL_DATA_VALIDATION_MISSING" in warnings: next_steps.append("使用独立真实观测数据完成验证。")
    if "DATA_READINESS_INCOMPLETE" in warnings: next_steps.append("返回数据页面处理缺失、映射、单位或 CRS 问题。")
    if not findings: next_steps.append("选择场景并完成一次运行。")
    return ResultInterpretation(headline, summary, findings, tuple(warnings), limits, tuple(next_steps))
