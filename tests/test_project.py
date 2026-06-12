from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import zipfile

import pandas as pd

from hydrolite.project import (
    compare_project_outputs,
    create_project,
    export_project_package,
    list_project_cases,
    project_info,
    run_project_batch,
    run_project_case,
    validate_project,
)


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_project_case(project_dir: Path, name: str = "demo") -> Path:
    case = project_dir / "cases" / f"{name}.yaml"
    case.write_text(
        f"""
name: {name}

model:
  time_step_hours: 1.0

inputs:
  directory: {Path.cwd() / "data_demo"}
  rainfall: rainfall.csv
  subcatchments: subcatchments.csv
  reaches: reaches.csv

outputs:
  directory: output/{name}
""".lstrip(),
        encoding="utf-8",
    )
    for stale in (project_dir / "cases").glob("demo_*.yaml"):
        stale.unlink()
    return case


def test_project_create_info_and_case_listing(tmp_path: Path):
    project_dir = tmp_path / "demo_project"
    summary = create_project(project_dir)

    assert (project_dir / "project.yaml").exists()
    assert summary.exists()
    for name in ("cases", "configs", "data", "output", "reports", "logs"):
        assert (project_dir / name).exists()

    info = project_info(project_dir)
    assert info["project"]["project_id"] == "demo_project"
    assert {"demo.yaml", "demo_gee.yaml", "demo_swmm.yaml"}.issubset({path.name for path in list_project_cases(project_dir)})


def test_project_validate_run_batch_compare_and_export(tmp_path: Path):
    before = _snapshot_data_raw()
    project_dir = tmp_path / "demo_project"
    create_project(project_dir)
    _write_project_case(project_dir, "demo")

    validation = validate_project(project_dir)
    assert Path(validation["xlsx"]).exists()
    assert Path(validation["report_md"]).exists()
    checks = pd.read_excel(validation["xlsx"], sheet_name="project_checks")
    assert {"check_group", "check_name", "status", "message"}.issubset(checks.columns)

    outputs = run_project_case(project_dir, "demo.yaml")
    assert outputs.result_flow_csv.exists()
    assert outputs.output_dir == (project_dir / "output" / "demo").resolve()

    summary_path, rows, failed = run_project_batch(project_dir)
    assert summary_path.exists()
    assert not failed
    assert rows[0]["status"] == "success"

    comparison = compare_project_outputs(project_dir)
    assert comparison.xlsx.exists()
    assert comparison.csv.exists()
    assert comparison.report_md.exists()

    (project_dir / "reports" / "model.pt").write_text("weight", encoding="utf-8")
    (project_dir / ".streamlit").mkdir()
    (project_dir / ".streamlit" / "secrets.toml").write_text("secret='x'", encoding="utf-8")
    package = export_project_package(project_dir)
    assert package.exists()
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
    assert "project.yaml" in names
    assert "cases/demo.yaml" in names
    assert not any(name.endswith((".pt", ".pth", ".ckpt", ".onnx")) for name in names)
    assert not any("secrets.toml" in name for name in names)
    assert not any(name.startswith("external/") for name in names)
    assert _snapshot_data_raw() == before


def test_project_cli_info_validate_and_export(tmp_path: Path):
    project_dir = tmp_path / "cli_project"
    create_project(project_dir)
    _write_project_case(project_dir, "demo")

    for command in (
        ["project", "info", str(project_dir)],
        ["project", "validate", str(project_dir)],
        ["project", "export", str(project_dir)],
    ):
        completed = subprocess.run(
            [sys.executable, "-m", "hydrolite", *command],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr


def test_streamlit_project_helpers_import():
    from hydrolite.ui.app import read_project_validation_outputs, scan_project_dirs

    assert isinstance(scan_project_dirs(Path("projects")), list)
    assert isinstance(read_project_validation_outputs(Path("projects/demo_project")), dict)
