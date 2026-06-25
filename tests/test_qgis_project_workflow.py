from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


ALPHA_TAG_COMMIT = "e81f194cbca58c3a88f8176b6da114d6a46ee1c6"
BETA_TAG_COMMIT = "67a386dd0de53ef7c22bdbd054adaf7c5aef122b"
BETA_1_TAG_COMMIT = "616fa6754b73b64d222ad508c1ab57bb52364365"
SUBBASINS = Path("data_demo/gis/demo_subbasins.geojson")
REACHES = Path("data_demo/gis/demo_reaches.geojson")
BASIN = Path("data_demo/gis/demo_basin_boundary.geojson")


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(Path("data_raw").rglob("*"))
        if path.is_file()
    }


def _converted_inputs(tmp_path: Path) -> Path:
    from hydrolite.qgis_bridge import convert_qgis_layers_to_hydrolite_inputs

    output_dir = tmp_path / "qgis_to_hydrolite"
    result = convert_qgis_layers_to_hydrolite_inputs(SUBBASINS, REACHES, BASIN, output_dir)
    assert result["status"] == "success"
    return output_dir


def test_qgis_project_workflow_functions(tmp_path: Path):
    from hydrolite.qgis_bridge import (
        copy_qgis_outputs_to_project,
        create_project_from_qgis_outputs,
        generate_case_from_qgis_outputs,
        generate_project_yaml_from_qgis_outputs,
        run_qgis_project_workflow,
    )

    qgis_output = _converted_inputs(tmp_path)
    project = tmp_path / "qgis_project"
    copied = copy_qgis_outputs_to_project(qgis_output, project)
    assert Path(copied["copied"]["subbasins.csv"]).exists()
    assert generate_project_yaml_from_qgis_outputs(qgis_output, project).exists()
    assert generate_case_from_qgis_outputs(qgis_output, project).exists()

    full_project = tmp_path / "qgis_full_project"
    created = create_project_from_qgis_outputs(qgis_output, full_project)
    assert created["status"] == "success"
    assert (full_project / "project.yaml").exists()
    assert (full_project / "cases" / "qgis_demo.yaml").exists()
    assert (full_project / "reports" / "qgis_project_summary.md").exists()

    workflow = run_qgis_project_workflow(qgis_output, tmp_path / "qgis_workflow_project", run_batch=True, run_compare=True, run_report=True)
    assert workflow["status"] == "success"
    assert workflow["batch"]["status"] == "success"
    assert workflow["compare"]["status"] == "success"
    assert Path(workflow["summary"]).exists()


def test_qgis_project_workflow_cli(tmp_path: Path):
    qgis_output = _converted_inputs(tmp_path)
    project = tmp_path / "cli_project"
    workflow_project = tmp_path / "cli_workflow_project"
    commands = [
        ("qgis", "create-project", str(qgis_output), str(project)),
        ("project", "validate", str(project)),
        ("project", "batch", str(project)),
        ("project", "compare", str(project)),
        ("report", "project", str(project)),
        ("qgis", "project-workflow", str(qgis_output), str(workflow_project)),
        ("project", "validate", str(workflow_project)),
        ("project", "batch", str(workflow_project)),
        ("project", "compare", str(workflow_project)),
        ("report", "project", str(workflow_project)),
    ]
    for command in commands:
        completed = subprocess.run(
            [sys.executable, "-m", "hydrolite", *command],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert completed.returncode == 0, completed.stderr


def test_qgis_project_workflow_refuses_existing_project(tmp_path: Path):
    from hydrolite.qgis_bridge import create_project_from_qgis_outputs

    qgis_output = _converted_inputs(tmp_path)
    project = tmp_path / "existing"
    project.mkdir()
    (project / "keep.txt").write_text("do not overwrite\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        create_project_from_qgis_outputs(qgis_output, project)


def test_qgis_project_workflow_streamlit_imports():
    import hydrolite.ui.pages.qgis_bridge as qgis_bridge_page

    assert callable(qgis_bridge_page.render)


def test_qgis_project_workflow_does_not_modify_data_raw(tmp_path: Path):
    from hydrolite.qgis_bridge import create_project_from_qgis_outputs

    before = _snapshot_data_raw()
    qgis_output = _converted_inputs(tmp_path)
    create_project_from_qgis_outputs(qgis_output, tmp_path / "project")
    assert _snapshot_data_raw() == before


def test_qgis_project_workflow_no_secrets_or_weights_and_tags_unchanged():
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60).stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)
    for tag, commit in {
        "v0.5.0-alpha.2": ALPHA_TAG_COMMIT,
        "v0.6.0-beta": BETA_TAG_COMMIT,
        "v0.6.0-beta.1": BETA_1_TAG_COMMIT,
    }.items():
        completed = subprocess.run(["git", "rev-parse", tag], capture_output=True, text=True, check=False, timeout=60)
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == commit
