from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_TAGS = {
    "v0.5.0-alpha.2": "e81f194cbca58c3a88f8176b6da114d6a46ee1c6",
    "v0.6.0-beta": "67a386dd0de53ef7c22bdbd054adaf7c5aef122b",
    "v0.6.0-beta.1": "616fa6754b73b64d222ad508c1ab57bb52364365",
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hydrolite", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _hms_project(tmp_path: Path) -> Path:
    root = tmp_path / "hms_project"
    (root / "run").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "scripts").mkdir()
    (root / "HydroLite_HMS_Project.hms").write_text("Project: HydroLite_HMS_Project\nEnd:\n", encoding="utf-8")
    (root / "run" / "hydrolite_run.run").write_text("Run: hydrolite_run\nEnd:\n", encoding="utf-8")
    return root


def _data_raw_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "data_raw").rglob("*"))
        if path.is_file()
    }


def test_hms_run_functions_and_reports(tmp_path: Path):
    from hydrolite.hec_hms import (
        build_hms_run_command,
        collect_hms_run_outputs,
        detect_hms_cli_modes,
        parse_hms_logs,
        run_hms_probe,
        run_hms_project,
        summarize_hms_run,
        validate_hms_run_outputs,
        write_hms_run_scripts,
    )

    root = _hms_project(tmp_path)
    modes = detect_hms_cli_modes()
    assert modes["status"] in {"partial", "unavailable"}
    command = build_hms_run_command(root)
    assert {"executable", "args", "cwd", "environment", "mode", "confidence", "warnings", "dry_run_command_string"} <= set(command)
    scripts = write_hms_run_scripts(root)
    assert all(path.exists() for path in scripts.values())
    custom_scripts = write_hms_run_scripts(root, tmp_path / "custom_scripts")
    assert str(custom_scripts["jython"]) in custom_scripts["shell"].read_text(encoding="utf-8")
    probe = run_hms_probe(timeout=10)
    assert probe["status"] in {"completed_probe", "probe_timeout", "failed", "unavailable"}
    result = run_hms_project(root, execute=False)
    assert result["runnable_status"] == "dry_run"
    outputs = collect_hms_run_outputs(root)
    assert outputs["status"] == "success"
    logs = parse_hms_logs(root)
    assert {"ERROR", "WARNING", "Simulation", "Compute", "DSS"} <= set(logs["keyword_counts"])
    summary = summarize_hms_run(root)
    assert Path(summary["summary_xlsx"]).exists()
    assert Path(summary["run_report"]).exists()
    assert Path(summary["run_result_json"]).exists()
    assert "overview" in pd.ExcelFile(summary["summary_xlsx"]).sheet_names
    validation = validate_hms_run_outputs(root)
    assert validation["status"] == "passed"
    assert validation["runnable_status"] == "dry_run"
    assert json.loads((root / "reports" / "hec_hms_run_result.json").read_text(encoding="utf-8"))["execute_requested"] is False


def test_hms_run_cli_commands(tmp_path: Path):
    root = _hms_project(tmp_path)
    commands = (
        ("hms", "cli-modes"),
        ("hms", "run-command", str(root)),
        ("hms", "write-run-scripts", str(root)),
        ("hms", "run-probe"),
        ("hms", "run", str(root), "--dry-run"),
        ("hms", "collect-outputs", str(root)),
        ("hms", "parse-logs", str(root)),
        ("hms", "run-summary", str(root)),
        ("hms", "validate-run", str(root)),
    )
    for command in commands:
        result = _run(*command)
        assert result.returncode == 0, result.stdout + result.stderr


def test_hms_unavailable_is_graceful(monkeypatch, tmp_path: Path):
    import hydrolite.hec_hms as hms

    monkeypatch.setattr(hms, "_first_hec_hms_executable", lambda: None)
    root = _hms_project(tmp_path)
    assert hms.build_hms_run_command(root)["mode"] == "unavailable"
    assert hms.run_hms_probe()["status"] == "unavailable"
    result = hms.run_hms_project(root, execute=False)
    assert result["runnable_status"] == "unavailable"
    assert (root / "reports" / "hec_hms_run_report.md").exists()


def test_hms_run_ui_workflow_and_safety(tmp_path: Path):
    import hydrolite.ui.pages.hec_hms as page
    from hydrolite.hec_hms import run_hms_project
    from hydrolite.workflow_engine import get_workflow_stage

    assert callable(page.render)
    stage = get_workflow_stage("hec_hms_run")
    assert stage["status"] == "partial"
    assert stage["cli_command"].endswith("--dry-run")
    assert "DSS" in stage["implementation_notes"]
    before = _data_raw_hashes()
    run_hms_project(_hms_project(tmp_path), execute=False)
    assert _data_raw_hashes() == before
    for tag, expected in PROTECTED_TAGS.items():
        completed = subprocess.run(["git", "rev-parse", tag], cwd=ROOT, capture_output=True, text=True, check=False)
        assert completed.stdout.strip() == expected
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.splitlines()
    assert not any(path.startswith("external/") for path in tracked)
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
