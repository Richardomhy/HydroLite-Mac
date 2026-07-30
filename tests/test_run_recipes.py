def test_builtin_recipes_are_copyable():
    from hydrolite.run_recipes import copy_run_recipe, list_run_recipes
    rows = list_run_recipes()
    assert {row["recipe_id"] for row in rows} >= {"data_preparation","full_modeling_workflow","reporting_only"}
    recipe = copy_run_recipe("data_preparation"); recipe["stages"].append("custom")
    assert "custom" not in copy_run_recipe("data_preparation")["stages"]
