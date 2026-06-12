from pathlib import Path
import subprocess
import sys

import pandas as pd
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
    assert "temperature" in supported
    metadata = get_dataset_metadata("DEM")
    assert metadata["dataset_name"] == "DEM"
    assert metadata["gee_id"] == "USGS/SRTMGL1_003"
    temp = get_dataset_metadata("temperature")
    assert temp["gee_id"] == "ECMWF/ERA5_LAND/DAILY_AGGR"
    assert "temperature_2m" in temp["bands"]


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
        [sys.executable, "-m", "hydrolite", "gee", "hydrolite-inputs", "configs/gee.example.yaml"],
    ):
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)
        assert completed.returncode == 0, completed.stderr
    assert Path("output/gee/gee_data_plan.xlsx").exists()
    assert Path("output/gee/gee_summary.xlsx").exists()
    assert Path("output/gee/gee_report.md").exists()
    assert Path("output/gee/hydrolite_inputs/gee_basin_summary.xlsx").exists()
    assert Path("output/gee/hydrolite_inputs/gee_chirps_rainfall.csv").exists()
    assert Path("output/gee/hydrolite_inputs/gee_temperature_daily.csv").exists()
    assert Path("output/gee/hydrolite_inputs/gee_parameter_suggestions.xlsx").exists()
    assert Path("output/gee/hydrolite_inputs/gee_parameter_suggestions.yaml").exists()


def test_gee_hydrolite_input_products_are_parseable():
    from hydrolite.routing import validate_muskingum_parameters

    rainfall = Path("output/gee/hydrolite_inputs/gee_chirps_rainfall.csv")
    temperature = Path("output/gee/hydrolite_inputs/gee_temperature_daily.csv")
    suggestions = Path("output/gee/hydrolite_inputs/gee_parameter_suggestions.yaml")
    subbasins = Path("data_demo/gee/gee_subbasins.csv")
    reaches = Path("data_demo/gee/gee_reaches.csv")
    if not rainfall.exists() or not suggestions.exists():
        completed = subprocess.run(
            [sys.executable, "-m", "hydrolite", "gee", "hydrolite-inputs", "configs/gee.example.yaml"],
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
        assert completed.returncode == 0, completed.stderr
    rain = __import__("pandas").read_csv(rainfall)
    assert {"datetime", "subbasin_id", "rain_mm"}.issubset(rain.columns)
    temp = pd.read_csv(temperature)
    assert {"datetime", "basin_id", "temperature_mean_c", "temperature_source"}.issubset(temp.columns)
    values = pd.to_numeric(temp["temperature_mean_c"], errors="coerce")
    if values.notna().any():
        assert values.between(-80, 60).all()
    parsed = yaml.safe_load(suggestions.read_text(encoding="utf-8"))
    assert "suggested_cn" in parsed
    if subbasins.exists():
        sub = __import__("pandas").read_csv(subbasins)
        assert {"id", "area_km2", "curve_number", "lag_hours"}.issubset(sub.columns)
    if reaches.exists():
        reach = __import__("pandas").read_csv(reaches)
        assert {"id", "K_hours", "X"}.issubset(reach.columns)
        row = reach.iloc[0]
        validate_muskingum_parameters(str(row["id"]), float(row["K_hours"]), float(row["X"]), 24.0)


def test_demo_gee_validates_if_generated():
    case = Path("cases/demo_gee.yaml")
    if case.exists():
        rainfall = Path("output/gee/hydrolite_inputs/gee_chirps_rainfall.csv")
        if rainfall.exists():
            rain = pd.read_csv(rainfall)
            if "status" in rain.columns and not (rain["status"] == "available").any():
                return
        completed = subprocess.run(
            [sys.executable, "-m", "hydrolite", "validate", str(case)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr


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
