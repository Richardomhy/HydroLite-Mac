from __future__ import annotations

import json


def test_real_project_model_cli_delegates_without_running_data(monkeypatch, tmp_path, capsys):
    import hydrolite.real_project_model as model
    from hydrolite.__main__ import main

    captured = {}

    def fake_run(source_root, *, workspace_dir, baseline_output_dir):
        captured.update(source_root=source_root, workspace_dir=workspace_dir, output_dir=baseline_output_dir)
        return {
            "status": "passed", "output_dir": tmp_path / "output" / "m8b",
            "version": {"project_version_id": "pv_test"},
            "run": {"run_id": "run_test"},
            "deliverable": {"deliverable_id": "del_test", "review_status": "reviewed"},
            "gate": "ready_with_warnings",
        }

    monkeypatch.setattr(model, "run_real_project_model_validation", fake_run)
    assert main([
        "real-project", "model", "anonymous-source",
        "--workspace-dir", str(tmp_path / "workspace"),
        "--output-dir", str(tmp_path / "output"),
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert captured == {
        "source_root": "anonymous-source",
        "workspace_dir": str(tmp_path / "workspace"),
        "output_dir": str(tmp_path / "output"),
    }
    assert payload["run_id"] == "run_test"
    assert payload["scientific_status"] == "real_data_diagnostic"


def test_real_project_model_workflow_and_recipe_contract():
    from hydrolite.run_recipes import get_run_recipe
    from hydrolite.workflow_engine import get_workflow_stage

    stage = get_workflow_stage("real_project_model_validation")
    recipe = get_run_recipe("real_project_model_validation")
    assert stage["status"] == "partial"
    assert "real-project model" in stage["cli_command"]
    assert recipe["validation_level"] == "real_data_diagnostic"
    assert recipe["stages"][0] == "real_project_model_validation"
    assert any("water_quality" in item and "planned" in item for item in recipe["limitations"])
