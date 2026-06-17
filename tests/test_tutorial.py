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


def test_tutorial_module_imports():
    import hydrolite.tutorial as tutorial

    assert callable(tutorial.get_demo_steps)
    assert callable(tutorial.generate_demo_summary)


def test_demo_steps_are_complete():
    from hydrolite.tutorial import REQUIRED_STEP_FIELDS, get_demo_steps

    steps = get_demo_steps()
    assert steps
    for step in steps:
        assert REQUIRED_STEP_FIELDS.issubset(step)
        assert step["step_id"]
        assert isinstance(step["success_files"], list)


def test_tutorial_checklist_summary_and_reset(tmp_path: Path):
    from hydrolite.tutorial import (
        generate_demo_summary,
        get_demo_checklist,
        reset_demo_progress,
        write_demo_progress,
    )

    before = _snapshot_data_raw()
    project = tmp_path / "demo_project"
    (project / "reports").mkdir(parents=True)
    (project / "output" / "demo_gee").mkdir(parents=True)
    output = project / "output" / "demo_gee" / "result_flow.csv"
    output.write_text("time,outflow_cms\n2026-01-01,1.0\n", encoding="utf-8")

    write_demo_progress(project, ["intro", "run_demo_gee"])
    checklist = get_demo_checklist(project)
    assert checklist
    assert any(row["marked_complete"] for row in checklist)
    summary = generate_demo_summary(project)
    assert summary.exists()
    assert "HydroLite Studio Demo Summary" in summary.read_text(encoding="utf-8")

    reset_demo_progress(project)
    assert output.exists(), "reset must not delete project outputs"
    assert _snapshot_data_raw() == before


def test_tutorial_cli_commands_execute():
    for command in (
        [sys.executable, "-m", "hydrolite", "tutorial", "list"],
        [sys.executable, "-m", "hydrolite", "tutorial", "checklist", "projects/demo_project"],
        [sys.executable, "-m", "hydrolite", "tutorial", "summary", "projects/demo_project"],
        [sys.executable, "-m", "hydrolite", "tutorial", "reset", "projects/demo_project"],
    ):
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    assert Path("projects/demo_project/reports/demo_summary.md").exists()


def test_tutorial_streamlit_pages_import():
    import hydrolite.ui.app as app
    import hydrolite.ui.pages.tutorial_demo as page

    assert callable(page.render)
    assert "教程与 Demo" in app.PAGES


def test_tutorial_no_tracked_secrets_weights_or_external_repo():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    tracked = completed.stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/") for path in tracked)
