from hydrolite.run_recipes import get_run_recipe
from hydrolite.scenario_registry import get_scenario, list_scenarios


def test_every_scenario_maps_to_existing_workflow_recipe():
    for row in list_scenarios():
        recipe = get_run_recipe(row["workflow_id"])
        assert recipe["recipe_id"] == row["workflow_id"]
    assert get_scenario("SC01").workflow_id == "hindcast_validation_full"
    assert get_scenario("SC03").workflow_id == "current_drought_monitoring"
    assert get_scenario("SC07").workflow_id == "water_quality_multistation_experiment"
    assert get_scenario("SC08").workflow_id == "flood_susceptibility_mapping"
    assert get_scenario("SC10").workflow_id == "gee_dataset_discovery"
