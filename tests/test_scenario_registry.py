from hydrolite.scenario_registry import get_scenario, list_scenarios, scenario_status_counts, validate_scenario_registry


def test_registry_contains_twelve_business_scenarios_with_complete_contracts():
    rows = list_scenarios(); assert [row["scenario_id"] for row in rows] == [f"SC{i:02d}" for i in range(1, 13)]
    required = {"scenario_id", "name_zh", "name_en", "business_question", "required_data", "optional_data", "automatic_data_sources", "capabilities", "workflow_id", "readiness_rules", "output_types", "validation_level", "production_status", "limitations", "recommended_for", "not_recommended_for", "advanced"}
    assert all(required.issubset(row) for row in rows)
    assert validate_scenario_registry()["status"] == "passed"


def test_scenario_statuses_preserve_product_boundaries():
    counts = scenario_status_counts()
    assert counts == {"production_ready": 1, "ready_with_warnings": 8, "experimental": 3, "planned": 0, "unavailable": 0}
    assert get_scenario("SC07").production_status == "experimental"
    assert get_scenario("SC08").production_status == "experimental"
    assert "Gamma" not in {item.name_en for item in map(get_scenario, [f"SC{i:02d}" for i in range(1, 13)])}
