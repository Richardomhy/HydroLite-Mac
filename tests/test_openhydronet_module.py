from pathlib import Path
import subprocess
import sys

import yaml


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_openhydronet_module_imports_without_environment(monkeypatch):
    monkeypatch.delenv("OPENHYDRONET_HOME", raising=False)
    from hydrolite.openhydronet.adapter import describe_openhydronet_adapter
    from hydrolite.openhydronet.runner import (
        detect_openhydronet_environment,
        explain_missing_environment,
        run_openhydronet_smoke,
    )

    env = detect_openhydronet_environment()
    assert env["status"] in {"available", "unavailable", "failed"}
    assert "repo_path" in env
    assert "torch_status" in env
    assert "placeholder" in describe_openhydronet_adapter()["status"]
    assert "OPENHYDRONET_HOME" in explain_missing_environment()
    result = run_openhydronet_smoke("configs/openhydronet.example.yaml")
    assert result["status"] in {"passed", "unavailable", "failed", "skipped"}


def test_openhydronet_example_config_exists_and_parses():
    path = Path("configs/openhydronet.example.yaml")
    assert path.exists()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["mode"] == "placeholder"
    assert "forecast" in data


def test_openhydronet_config_loader_and_validator():
    from hydrolite.openhydronet.config import (
        load_openhydronet_config,
        validate_openhydronet_config,
    )

    config = load_openhydronet_config(Path("configs/openhydronet.example.yaml"))
    result = validate_openhydronet_config(config)
    assert result["status"] == "passed"


def test_diagnose_openhydronet_runs_and_writes_output():
    before = _snapshot_data_raw()
    completed = subprocess.run(
        [sys.executable, "scripts/diagnose_openhydronet.py"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    output = Path("output/openhydronet_diagnosis.txt")
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "python_version" in text
    assert "repo_path" in text
    assert _snapshot_data_raw() == before


def test_openhydronet_cli_commands_and_smoke_outputs():
    before = _snapshot_data_raw()
    for command in (
        [sys.executable, "-m", "hydrolite", "openhydronet", "diagnose"],
        [sys.executable, "-m", "hydrolite", "openhydronet", "smoke", "configs/openhydronet.example.yaml"],
    ):
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
        assert completed.returncode == 0, completed.stderr
    assert Path("output/openhydronet/smoke_test_summary.xlsx").exists()
    assert Path("output/openhydronet/smoke_test_report.md").exists()
    assert _snapshot_data_raw() == before


def test_openhydronet_env_scripts_run_without_crashing():
    for script in (
        "scripts/openhydronet_env/test_openhydronet_env.py",
        "scripts/openhydronet_env/run_openhydronet_smoke.py",
    ):
        completed = subprocess.run([sys.executable, script], capture_output=True, text=True, check=False, timeout=90)
        assert completed.returncode == 0, completed.stderr
    assert Path("output/openhydronet_env/test_env_report.txt").exists()


def test_openhydronet_gitignore_guards_large_external_assets():
    text = Path(".gitignore").read_text(encoding="utf-8")
    for pattern in ("external/", "*.pt", "*.pth", "*.ckpt", "*.onnx", "checkpoints/", "model_weights/"):
        assert pattern in text


def test_streamlit_openhydronet_panel_helpers_import():
    from hydrolite.ui.app import get_openhydronet_panel_payload

    payload = get_openhydronet_panel_payload()
    assert payload["stage"] == "environment diagnosis / smoke test only"
    assert "environment" in payload
    assert "smoke_summary" in payload
