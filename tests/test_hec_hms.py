from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
SWMM_INP = ROOT / "data_raw" / "swmm" / "demo.inp"
PROTECTED_TAGS = {
    "v0.5.0-alpha.2": "e81f194cbca58c3a88f8176b6da114d6a46ee1c6",
    "v0.6.0-beta": "67a386dd0de53ef7c22bdbd054adaf7c5aef122b",
    "v0.6.0-beta.1": "616fa6754b73b64d222ad508c1ab57bb52364365",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hydrolite", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "qgis_workflow_project"
    (project / "cases").mkdir(parents=True)
    (project / "data").mkdir()
    (project / "reports").mkdir()
    (project / "output").mkdir()
    (project / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "project_name": "HEC-HMS Test Project",
                "project_id": "hec_hms_test",
                "paths": {"cases_dir": "cases", "data_dir": "data", "output_dir": "output", "reports_dir": "reports"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (project / "cases" / "demo.yaml").write_text("case_name: demo\n", encoding="utf-8")
    shutil.copy2(ROOT / "templates" / "data" / "examples" / "subbasins_example.csv", project / "data" / "subbasins.csv")
    shutil.copy2(ROOT / "templates" / "data" / "examples" / "reaches_example.csv", project / "data" / "reaches.csv")
    shutil.copy2(ROOT / "templates" / "data" / "examples" / "rainfall_example.csv", project / "data" / "rainfall.csv")
    return project


def test_hec_hms_module_and_diagnosis(tmp_path: Path):
    import hydrolite.hec_hms as hms

    assert callable(hms.create_hms_project_from_hydrolite)
    assert hms.detect_hec_hms_installations()
    assert hms.detect_hec_hms_executables()
    diagnosis = hms.build_hec_hms_diagnosis()
    assert diagnosis["recommended_integration"] in {"command_line_available", "project_generation_only", "unavailable"}
    outputs = hms.write_hec_hms_diagnosis(tmp_path / "diagnosis")
    assert outputs["md"].exists()
    assert outputs["json"].exists()


def test_collect_and_create_hms_project(tmp_path: Path):
    from hydrolite.hec_hms import collect_hydrolite_project_for_hms, create_hms_project_from_hydrolite, validate_hms_project

    project = _project(tmp_path)
    data = collect_hydrolite_project_for_hms(project)
    assert len(data["subbasins"]) > 0
    assert len(data["reaches"]) > 0
    assert len(data["rainfall"]) > 0
    output = tmp_path / "hms_project"
    result = create_hms_project_from_hydrolite(project, output)
    assert result["status"] == "project_generation_mvp"
    assert result["runnable_status"] == "unverified"
    validation = validate_hms_project(output)
    assert validation["status"] == "passed"
    for name in (
        "HydroLite_HMS_Project.hms",
        "reports/hec_hms_project_report.md",
        "reports/hec_hms_project_manifest.json",
        "reports/hec_hms_mapping_summary.xlsx",
    ):
        assert (output / name).exists()
    manifest = json.loads((output / "reports" / "hec_hms_project_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mapping_counts"]["subbasins"] > 0
    assert set(pd.ExcelFile(output / "reports" / "hec_hms_mapping_summary.xlsx").sheet_names) == {
        "subbasin_mapping",
        "reach_mapping",
        "rainfall_mapping",
        "summary",
    }


def test_hms_cli_commands(tmp_path: Path):
    project = _project(tmp_path)
    output = tmp_path / "hms_cli_project"
    for command in (
        ("hms", "paths"),
        ("hms", "diagnose"),
        ("hms", "version"),
        ("hms", "create-project", str(project), str(output)),
        ("hms", "validate", str(output)),
        ("hms", "report", str(output)),
    ):
        result = _run(*command)
        assert result.returncode == 0, result.stdout + result.stderr


def test_hms_streamlit_and_workflow_states():
    import hydrolite.ui.pages.hec_hms as hms_page
    from hydrolite.workflow_engine import get_workflow_stage

    assert callable(hms_page.render)
    project_stage = get_workflow_stage("hec_hms_project")
    run_stage = get_workflow_stage("hec_hms_run")
    assert project_stage["status"] == "partial"
    assert run_stage["status"] == "partial"
    assert "hec_hms_project_report.md" in project_stage["expected_outputs"]
    assert (ROOT / "docs" / "hec_hms_project_generator.md").exists()
    assert (ROOT / "docs" / "hec_hms_run_mvp.md").exists()


def test_hms_does_not_modify_data_raw_or_tags():
    before = _sha256(SWMM_INP)
    assert _run("hms", "paths").returncode == 0
    assert _sha256(SWMM_INP) == before
    for tag, expected in PROTECTED_TAGS.items():
        completed = subprocess.run(["git", "rev-parse", tag], cwd=ROOT, capture_output=True, text=True, check=False)
        assert completed.stdout.strip() == expected


def test_hms_files_do_not_track_secrets_external_or_weights():
    completed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False)
    tracked = completed.stdout.splitlines()
    assert not any(path.startswith("external/") for path in tracked)
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
