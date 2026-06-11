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
    assert status["initialization"]["status"] in {"available", "unavailable", "failed"}
    supported = list_supported_datasets()
    assert "DEM" in supported
    assert "precipitation" in supported
    assert "surface_water" in supported
    metadata = get_dataset_metadata("DEM")
    assert metadata["dataset_name"] == "DEM"
    assert metadata["gee_id"] == "USGS/SRTMGL1_003"


def test_gee_example_config_exists_and_parses():
    path = Path("configs/gee.example.yaml")
    assert path.exists()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "datasets" in data
    assert "export" in data
    assert data["basin_boundary"] == "data_demo/gee/demo_basin.geojson"


def test_gee_local_example_config_exists_and_parses():
    path = Path("configs/gee.local.example.yaml")
    assert path.exists()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["project"] == "your-gee-project-id"


def test_demo_basin_geojson_bbox_can_be_read():
    from hydrolite.gee.basin import get_boundary_bbox

    path = Path("data_demo/gee/demo_basin.geojson")
    assert path.exists()
    bbox = get_boundary_bbox(path)
    assert bbox["status"] == "available"
    assert bbox["bbox"] == [120.12, 30.12, 120.16, 30.16]


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


def test_gee_cli_commands_run_without_crashing():
    for command in (
        [sys.executable, "-m", "hydrolite", "gee", "diagnose"],
        [sys.executable, "-m", "hydrolite", "gee", "plan", "configs/gee.example.yaml"],
        [sys.executable, "-m", "hydrolite", "gee", "summarize", "configs/gee.example.yaml"],
    ):
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
        assert completed.returncode == 0, completed.stderr
    assert Path("output/gee/gee_data_plan.xlsx").exists()
    assert Path("output/gee/gee_summary.xlsx").exists()
    assert Path("output/gee/gee_report.md").exists()


def test_streamlit_gee_panel_helpers_import():
    from hydrolite.ui.app import get_gee_panel_payload

    payload = get_gee_panel_payload()
    assert "status" in payload
    assert "datasets" in payload
    assert "demo_basin_bbox" in payload


def test_gitignore_contains_gee_secret_rules():
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "configs/gee.local.yaml" in text
    assert ".streamlit/secrets.toml" in text
    assert "*service-account*.json" in text
    assert "*credentials*.json" in text
