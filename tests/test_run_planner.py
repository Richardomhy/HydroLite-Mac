from tests.runtime_helpers import configure_runtime, make_workspace


def test_plan_has_dependencies_and_optional_isolation(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path)
    from hydrolite.project_service import register_workspace_as_project
    from hydrolite.run_planner import build_run_plan, validate_run_plan
    project = register_workspace_as_project(make_workspace(tmp_path))
    plan = build_run_plan(project["project_id"], "data_preparation", {"run_mode":"test"})
    assert validate_run_plan(plan)["status"] == "passed"
    reporting = next(task for task in plan["tasks"] if task["stage_id"] == "reporting")
    assert reporting["dependencies"][0]["required"] is False
