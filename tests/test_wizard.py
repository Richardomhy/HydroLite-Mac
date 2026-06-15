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


def test_wizard_module_imports():
    import hydrolite.wizard as wizard

    assert callable(wizard.create_project_from_wizard)
    assert callable(wizard.validate_wizard_config)


def test_wizard_templates_exist():
    root = Path("templates/wizard")
    for name in ("basic_project.yaml", "hydrolite_only.yaml", "hydrolite_gee.yaml", "hydrolite_swmm.yaml", "full_demo.yaml"):
        assert (root / name).exists()


def test_wizard_preview_cli_executes():
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "wizard", "preview", "templates/wizard/basic_project.yaml"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Wizard Demo Project" in completed.stdout
    assert "wizard_demo.yaml" in completed.stdout


def test_wizard_create_project_and_validate(tmp_path: Path):
    from hydrolite.project import validate_project
    from hydrolite.wizard import create_project_from_wizard

    before = _snapshot_data_raw()
    project_dir = tmp_path / "wizard_demo_project"
    result = create_project_from_wizard("templates/wizard/basic_project.yaml", project_dir)

    assert result["project_yaml"].exists()
    assert (project_dir / "cases" / "wizard_demo.yaml").exists()
    assert (project_dir / "project_summary.md").exists()
    assert (project_dir / "reports" / "wizard_summary.md").exists()
    validation = validate_project(project_dir)
    assert validation["xlsx"].exists()
    assert _snapshot_data_raw() == before


def test_wizard_existing_project_does_not_overwrite(tmp_path: Path):
    from hydrolite.wizard import create_project_from_wizard

    project_dir = tmp_path / "wizard_demo_project"
    create_project_from_wizard("templates/wizard/basic_project.yaml", project_dir)
    marker = project_dir / "marker.txt"
    marker.write_text("keep", encoding="utf-8")
    try:
        create_project_from_wizard("templates/wizard/basic_project.yaml", project_dir)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Expected FileExistsError for existing project.")
    assert marker.read_text(encoding="utf-8") == "keep"


def test_project_wizard_page_imports():
    import hydrolite.ui.pages.project_wizard as page

    assert callable(page.render)


def test_no_tracked_secrets_large_weights_or_external_repo():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    tracked = completed.stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)
