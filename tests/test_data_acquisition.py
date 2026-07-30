from pathlib import Path


def test_acquisition_plan_and_dry_run(tmp_path: Path):
    from hydrolite.data_acquisition import create_acquisition_plan, execute_acquisition_plan, validate_acquisition_plan, write_acquisition_report
    from hydrolite.workspace import create_workspace

    root = tmp_path / "workspace"
    create_workspace(root, "Acquire")
    plan = create_acquisition_plan(root, "full_modeling_workflow")
    assert validate_acquisition_plan(plan)["status"] == "passed"
    result = execute_acquisition_plan(plan, execute=False)
    assert result["status"] == "dry_run"
    assert all(step["download_execute"] is False for step in result["steps"])
    assert write_acquisition_report(tmp_path / "report", plan)["json"].exists()
