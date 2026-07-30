from pathlib import Path


def test_input_builder_uses_standardized_not_raw(tmp_path: Path):
    from hydrolite.data_quality_center import run_workspace_quality_checks
    from hydrolite.data_upload import copy_upload_to_workspace
    from hydrolite.input_builder import build_all_inputs
    from hydrolite.workspace import create_workspace

    root = tmp_path / "workspace"
    create_workspace(root, "Builder")
    for name in ("rainfall_observed.csv", "subbasins.csv", "reaches.csv"):
        copy_upload_to_workspace(Path("templates/data_upload") / name, root)
    assert run_workspace_quality_checks(root)["status"] in {"ready", "ready_with_warnings"}
    result = build_all_inputs(root, tmp_path / "inputs")
    hydrolite = next(row for row in result["models"] if row["model_id"] == "hydrolite_event_model")
    assert hydrolite["status"] == "ready"
    assert result["validation"]["status"] == "passed"
    assert not any("raw" in Path(path).parts for path in hydrolite["files"].values())
    drought = next(row for row in result["models"] if row["model_id"] == "continuous_hydrology_drought")
    assert drought["status"] == "incomplete"
