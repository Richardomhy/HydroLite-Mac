from hydrolite.result_interpretation import interpret_result


def test_interpretation_only_uses_provided_metrics_and_exposes_validation_gap():
    result = interpret_result({"PR_AUC": .51}, validation_status="synthetic_demo", readiness="ready", limitations=["susceptibility is not risk"])
    assert result.key_findings == ("PR_AUC: 0.51",)
    assert "REAL_DATA_VALIDATION_MISSING" in result.warnings
    assert result.limitations == ("susceptibility is not risk",)


def test_empty_result_has_actionable_empty_state_without_invented_findings():
    result = interpret_result({}, validation_status="not_tested", readiness="missing")
    assert result.headline == "尚无可解释结果" and not result.key_findings
    assert "选择场景并完成一次运行。" in result.recommended_next_steps
