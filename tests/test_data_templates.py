from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_data_templates_module_imports():
    import hydrolite.data_templates as data_templates

    assert callable(data_templates.list_data_templates)
    assert callable(data_templates.validate_project_input_dataset)


def test_standard_and_example_templates_exist():
    standard = Path("templates/data")
    examples = standard / "examples"
    for name in (
        "rainfall_template.csv",
        "subbasins_template.csv",
        "reaches_template.csv",
        "observed_streamflow_template.csv",
        "swmm_inflow_mapping_template.csv",
        "gee_basin_boundary_template.geojson",
    ):
        assert (standard / name).exists()
    for name in (
        "rainfall_example.csv",
        "subbasins_example.csv",
        "reaches_example.csv",
        "observed_streamflow_example.csv",
        "swmm_inflow_mapping_example.csv",
        "gee_basin_boundary_example.geojson",
    ):
        assert (examples / name).exists()


def test_list_and_export_templates(tmp_path: Path):
    from hydrolite.data_templates import export_all_data_templates, export_data_template, list_data_templates

    templates = list_data_templates()
    assert templates
    rainfall = export_data_template("rainfall", tmp_path)
    assert rainfall.exists()
    assert rainfall.name == "rainfall_template.csv"
    paths = export_all_data_templates(tmp_path / "all")
    assert len(paths) >= len(templates) * 2
    assert (tmp_path / "all" / "examples" / "rainfall_example.csv").exists()


def test_validate_example_templates_pass():
    from hydrolite.data_templates import (
        validate_gee_basin_boundary_template,
        validate_observed_streamflow_template,
        validate_rainfall_template,
        validate_reaches_template,
        validate_subbasins_template,
        validate_swmm_inflow_mapping_template,
    )

    root = Path("templates/data/examples")
    checks = [
        validate_rainfall_template(root / "rainfall_example.csv"),
        validate_subbasins_template(root / "subbasins_example.csv"),
        validate_reaches_template(root / "reaches_example.csv"),
        validate_observed_streamflow_template(root / "observed_streamflow_example.csv"),
        validate_swmm_inflow_mapping_template(root / "swmm_inflow_mapping_example.csv"),
        validate_gee_basin_boundary_template(root / "gee_basin_boundary_example.geojson"),
    ]
    assert all(check["status"] == "passed" for check in checks), checks


def test_validate_project_input_dataset_and_summary(tmp_path: Path):
    from hydrolite.data_templates import (
        export_all_data_templates,
        validate_project_input_dataset,
        write_data_template_summary,
    )

    export_all_data_templates(tmp_path)
    result = validate_project_input_dataset(tmp_path / "examples")
    assert result["status"] == "passed"
    outputs = write_data_template_summary(tmp_path / "examples")
    assert outputs["md"].exists()
    assert outputs["xlsx"].exists()


def test_templates_cli_commands(tmp_path: Path):
    before = _snapshot_data_raw()
    export_dir = tmp_path / "templates_export"
    for command in (
        [sys.executable, "-m", "hydrolite", "templates", "list"],
        [sys.executable, "-m", "hydrolite", "templates", "export", "rainfall", str(export_dir)],
        [sys.executable, "-m", "hydrolite", "templates", "export-all", str(export_dir)],
        [sys.executable, "-m", "hydrolite", "templates", "validate", "templates/data/examples/"],
        [sys.executable, "-m", "hydrolite", "templates", "summary", str(export_dir)],
    ):
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (export_dir / "data_template_summary.md").exists()
    assert (export_dir / "data_template_summary.xlsx").exists()
    assert _snapshot_data_raw() == before


def test_data_templates_streamlit_and_wizard_import():
    import hydrolite.ui.pages.data_templates as data_templates_page
    import hydrolite.ui.pages.project_wizard as project_wizard_page

    assert callable(data_templates_page.render)
    assert callable(project_wizard_page.render)


def test_data_templates_no_tracked_secrets_weights_or_external_repo():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    tracked = completed.stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/") for path in tracked)
