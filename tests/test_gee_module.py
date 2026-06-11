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


def test_gee_module_imports_without_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GEE_PROJECT", raising=False)
    from hydrolite.gee.auth import detect_gee_credentials, get_gee_status
    from hydrolite.gee.datasets import get_dataset_metadata, list_supported_datasets

    credentials = detect_gee_credentials()
    status = get_gee_status()
    assert "credential_sources_detected" in credentials
    assert status["initialization"]["status"] in {"available", "unavailable"}
    assert "DEM" in list_supported_datasets()
    assert get_dataset_metadata("DEM")["name"] == "DEM"


def test_gee_example_config_exists_and_parses():
    path = Path("configs/gee.example.yaml")
    assert path.exists()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "datasets" in data
    assert "export" in data


def test_diagnose_gee_runs_and_writes_output():
    before = _snapshot_data_raw()
    completed = subprocess.run(
        [sys.executable, "scripts/diagnose_gee.py"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    output = Path("output/gee_diagnosis.txt")
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "python_version" in text
    assert "gee_initialization_status" in text
    assert _snapshot_data_raw() == before


def test_streamlit_gee_panel_helpers_import():
    from hydrolite.ui.app import get_gee_panel_payload

    payload = get_gee_panel_payload()
    assert "status" in payload
    assert "datasets" in payload
