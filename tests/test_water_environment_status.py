from __future__ import annotations

from hydrolite.__main__ import main
from hydrolite.capability_registry import get_capability
from hydrolite.data_registry import get_dataset_type
from hydrolite.run_recipes import get_run_recipe
from hydrolite.ui.pages.water_environment_source_accounting import read_water_environment_outputs
from hydrolite.water_environment import run_water_environment_command, water_environment_status
from hydrolite.workflow_engine import get_workflow_stage


def test_capabilities_data_workflow_and_recipe_are_scoped():
    assert get_capability("water_environment_source_inventory")["status"] == "partial"
    assert get_capability("water_environment_load_accounting")["status"] == "partial"
    assert get_capability("water_environment_model")["status"] == "partial"
    assert get_capability("water_quality")["status"] == "planned"
    assert get_workflow_stage("pollution_source_inventory")["status"] == "partial"
    assert get_workflow_stage("source_load_accounting")["status"] == "partial"
    assert get_run_recipe("water_environment_source_accounting")["stages"] == ["pollution_source_inventory", "source_load_accounting", "reporting"]
    for dataset_type in ("pollution_source_inventory", "source_activity", "emission_factor", "treatment_factor"):
        assert get_dataset_type(dataset_type)["domain"] == "water_environment"


def test_status_cli_and_empty_output_are_graceful(tmp_path):
    assert water_environment_status(tmp_path)["water_quality"] == "planned"
    assert run_water_environment_command("ledger", output_dir=tmp_path)["status"] == "output_missing"
    assert main(["water-environment", "status", "--output-dir", str(tmp_path)]) == 0
    assert read_water_environment_outputs(tmp_path)["manifest"] == {}
