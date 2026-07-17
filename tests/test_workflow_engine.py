from __future__ import annotations

from pathlib import Path
import hashlib
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data_raw"
SWMM_INP = DATA_RAW / "swmm" / "demo.inp"
TEMPLATE = ROOT / "templates" / "workflows" / "full_modeling_workflow.yaml"
PROTECTED_TAGS = {
    "v0.5.0-alpha.2": "e81f194cbca58c3a88f8176b6da114d6a46ee1c6",
    "v0.6.0-beta": "67a386dd0de53ef7c22bdbd054adaf7c5aef122b",
    "v0.6.0-beta.1": "616fa6754b73b64d222ad508c1ab57bb52364365",
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "hydrolite", *args], cwd=ROOT, text=True, capture_output=True, check=False)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_workflow_engine_import_and_stage_schema():
    from hydrolite.workflow_engine import list_workflow_stages

    required = {
        "stage_id",
        "title_zh",
        "title_en",
        "description_zh",
        "description_en",
        "status",
        "required_inputs",
        "expected_outputs",
        "cli_command",
        "streamlit_page",
        "safety_notes",
        "dependencies",
        "implementation_notes",
    }
    stages = list_workflow_stages()
    assert stages
    assert {"hec_hms_project", "flood_forecast", "drought_forecast"} <= {stage["stage_id"] for stage in stages}
    for stage in stages:
        assert required <= set(stage)
        if stage["stage_id"] in {"flood_forecast", "drought_forecast"}:
            assert stage["status"] in {"planned", "not_implemented"}
        if stage["stage_id"] in {"hec_hms_project", "hec_hms_run"}:
            assert stage["status"] == "partial"


def test_workflow_templates_and_plan_outputs(tmp_path: Path):
    from hydrolite.workflow_engine import create_workflow_plan, validate_workflow_config

    for name in (
        "full_modeling_workflow.yaml",
        "qgis_to_report_workflow.yaml",
        "hec_hms_workflow_stub.yaml",
        "flood_drought_workflow_stub.yaml",
    ):
        assert (ROOT / "templates" / "workflows" / name).exists()
    validation = validate_workflow_config(TEMPLATE)
    assert validation["status"] == "passed"
    plan = create_workflow_plan(TEMPLATE, tmp_path / "plan")
    assert Path(plan["plan_json"]).exists()
    assert Path(plan["plan_md"]).exists()


def test_workflow_stage_and_full_dry_run(tmp_path: Path):
    from hydrolite.workflow_engine import (
        read_workflow_status,
        run_full_workflow,
        run_workflow_stage,
        summarize_workflow_outputs,
        write_workflow_report,
        write_workflow_status,
    )

    project = tmp_path / "project"
    result = run_workflow_stage("qgis_preprocessing", project, config_path=TEMPLATE, dry_run=True)
    assert result["run_status"] == "dry_run"
    full = run_full_workflow(project, config_path=TEMPLATE, dry_run=True)
    assert full["run_status"] == "dry_run"
    status_path = write_workflow_status(project, {"stage_runs": []})
    assert status_path.exists()
    assert read_workflow_status(project)["stage_runs"] == []
    report_path = write_workflow_report(project, {"runs": [result], "dry_run": True, "run_status": "dry_run"})
    assert report_path.exists()
    outputs = summarize_workflow_outputs(project)
    assert outputs["workflow_status"]["exists"]
    assert outputs["workflow_report"]["exists"]


def test_workflow_cli_commands(tmp_path: Path):
    project = tmp_path / "cli_project"
    commands = [
        ("workflow", "list"),
        ("workflow", "plan", str(TEMPLATE), str(tmp_path / "workflow_plan")),
        ("workflow", "status", str(project)),
        ("workflow", "run-stage", "qgis_preprocessing", str(project), "--dry-run"),
        ("workflow", "run-full", str(project), "--dry-run"),
    ]
    for command in commands:
        result = _run(*command)
        assert result.returncode == 0, result.stdout + result.stderr


def test_workflow_streamlit_and_docs_imports():
    import hydrolite.ui.pages.workflow_engine as workflow_page

    assert callable(workflow_page.render)
    for name in (
        "hec_hms_integration_plan.md",
        "full_modeling_workflow.md",
        "watershed_delineation_plan.md",
        "flood_forecast_plan.md",
        "drought_forecast_plan.md",
        "user_manual_plan.md",
    ):
        assert (ROOT / "docs" / name).exists()


def test_workflow_does_not_modify_data_raw_or_tags():
    before = _sha256(SWMM_INP)
    result = _run("workflow", "list")
    assert result.returncode == 0
    assert _sha256(SWMM_INP) == before
    for tag, expected in PROTECTED_TAGS.items():
        completed = subprocess.run(["git", "rev-parse", tag], cwd=ROOT, text=True, capture_output=True, check=False)
        assert completed.returncode == 0
        assert completed.stdout.strip() == expected


def test_no_obvious_secrets_or_weights_in_workflow_files():
    tracked_candidates = [
        ROOT / "hydrolite" / "workflow_engine.py",
        ROOT / "hydrolite" / "ui" / "pages" / "workflow_engine.py",
        ROOT / "templates" / "workflows" / "full_modeling_workflow.yaml",
    ]
    blocked = ("BEGIN PRIVATE KEY", "api_key:", "token:", "password:", ".pt", ".pth", ".ckpt", ".onnx")
    for path in tracked_candidates:
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in blocked)
