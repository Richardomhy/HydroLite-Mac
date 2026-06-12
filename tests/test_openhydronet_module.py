from pathlib import Path
import json
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
    assert "adapter" in describe_openhydronet_adapter()["status"]
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


def test_openhydronet_prepare_inputs_outputs_are_complete():
    before = _snapshot_data_raw()
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "openhydronet", "prepare-inputs", "configs/openhydronet.example.yaml"],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr
    root = Path("output/openhydronet/inputs")
    static = root / "static_attributes.csv"
    met = root / "meteorological_forcing.csv"
    flow = root / "hydrolite_streamflow.csv"
    metadata = root / "basin_metadata.json"
    manifest = root / "input_manifest.json"
    quality = root / "input_quality_report.xlsx"
    report = root / "openhydronet_input_report.md"
    for path in (static, met, flow, metadata, manifest, quality, report):
        assert path.exists(), path

    assert {
        "basin_id",
        "gauge_id",
        "area_km2",
        "dem_mean",
        "dem_min",
        "dem_max",
        "surface_water_occurrence_mean",
        "suggested_cn",
        "suggested_lag_hours",
        "suggested_muskingum_k_hours",
        "suggested_muskingum_x",
        "source",
    }.issubset(pd.read_csv(static).columns)
    assert {"datetime", "basin_id", "precipitation_mm", "temperature_mean_c"}.issubset(pd.read_csv(met).columns)
    assert {"datetime", "basin_id", "streamflow_m3s", "source_case"}.issubset(pd.read_csv(flow).columns)
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    assert {"basin_id", "gauge_id", "basin_boundary", "gee_project", "generated_at", "data_sources", "notes"}.issubset(meta)
    mani = json.loads(manifest.read_text(encoding="utf-8"))
    assert {"package_version", "generated_at", "files", "source_files", "row_counts", "warnings", "next_steps"}.issubset(mani)
    workbook = pd.ExcelFile(quality)
    assert {
        "overview",
        "static_attributes_checks",
        "meteorological_checks",
        "streamflow_checks",
        "warnings",
    }.issubset(set(workbook.sheet_names))
    warnings = pd.read_excel(quality, sheet_name="warnings")
    assert "temperature_mean_c_all_na" in set(warnings["warning_name"])
    assert "observed_streamflow_missing" in set(warnings["warning_name"])
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
    assert "input_package" in payload
