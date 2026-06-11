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
    )

    env = detect_openhydronet_environment()
    assert env["status"] == "placeholder_ready"
    assert "placeholder" in describe_openhydronet_adapter()["status"]
    assert "OPENHYDRONET_HOME" in explain_missing_environment()


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
    assert "placeholder_only" in text
    assert _snapshot_data_raw() == before


def test_streamlit_openhydronet_panel_helpers_import():
    from hydrolite.ui.app import get_openhydronet_panel_payload

    payload = get_openhydronet_panel_payload()
    assert payload["stage"] == "placeholder / not yet running real model"
    assert "environment" in payload
