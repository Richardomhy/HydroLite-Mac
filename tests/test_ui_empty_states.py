import importlib

from hydrolite.result_interpretation import interpret_result
from hydrolite.scenario_registry import assess_scenario_readiness
from hydrolite.ui.components.artifact_list import classify_artifact
from hydrolite.ui.pages.run_center import classify_runs


def test_empty_project_data_run_and_artifact_states_are_safe():
    readiness = assess_scenario_readiness("SC05", [])
    assert readiness.status == "missing_required_data" and readiness.next_recommended_action
    assert classify_runs([]) == {"active": [], "recent": [], "failed": [], "warnings": []}
    assert not interpret_result({}, validation_status="not_tested", readiness="missing").key_findings
    assert classify_artifact("result.csv") == "Table"


def test_all_top_level_and_special_pages_import_without_optional_dependencies():
    modules = ["project_home", "project_center", "scenario_center", "data_center", "run_center", "results_center", "research_methods_lab", "system_center", "gee_dataset_intelligence", "water_quality_lab", "flood_susceptibility"]
    for name in modules:
        module = importlib.import_module(f"hydrolite.ui.pages.{name}")
        assert callable(module.render)
