from pathlib import Path
import importlib

import pandas as pd

from hydrolite.runner import run_case


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_streamlit_app_imports():
    import streamlit_app
    import hydrolite.ui.app as app

    assert app.PROJECT_ROOT.exists()
    assert callable(streamlit_app.main)
    assert callable(app.main)


def test_ui_workbench_modules_import():
    modules = [
        "hydrolite.ui.components",
        "hydrolite.ui.state",
        "hydrolite.ui.pages.project_home",
        "hydrolite.ui.pages.data_validation",
        "hydrolite.ui.pages.scenario_run",
        "hydrolite.ui.pages.gee_center",
        "hydrolite.ui.pages.swmm_center",
        "hydrolite.ui.pages.openhydronet_center",
        "hydrolite.ui.pages.comparison",
        "hydrolite.ui.pages.report_export",
        "hydrolite.ui.pages.diagnostics",
    ]
    for module in modules:
        assert importlib.import_module(module)


def test_ui_case_scan_finds_demo_cases():
    from hydrolite.ui.app import scan_case_files, scan_project_dirs

    names = {path.name for path in scan_case_files(Path("cases"))}
    assert "demo.yaml" in names
    assert "demo_variant.yaml" in names
    assert isinstance(scan_project_dirs(Path("projects")), list)


def test_ui_reads_result_flow_and_water_balance():
    from hydrolite.ui.app import read_result_flow, read_water_balance

    outputs = run_case(Path("cases/demo.yaml"), output_dir=Path("output/demo"))
    result = read_result_flow(outputs.result_flow_csv)
    subbasin, outlet = read_water_balance(outputs.water_balance_xlsx)

    assert "outflow_cms" in result.columns
    assert pd.api.types.is_datetime64_any_dtype(result["time"])
    assert "balance_error_percent" in subbasin.columns
    assert "balance_error_percent" in outlet.columns


def test_ui_reads_swmm_outputs():
    from hydrolite.ui.app import read_swmm_outputs

    outputs = run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))
    tables = read_swmm_outputs(outputs.output_dir / "swmm")

    assert "summary" in tables
    assert "kpis" in tables
    assert "node_depth" in tables
    assert "link_flow" in tables
    assert "system" in tables
    assert "coupling" in tables


def test_ui_helpers_handle_missing_outputs_and_missing_project(monkeypatch, tmp_path: Path):
    from hydrolite.ui.app import is_streamlit_cloud
    from hydrolite.ui.components import (
        read_comparison_outputs,
        read_project_validation_outputs,
        read_result_flow,
        read_swmm_outputs,
        read_validation_outputs,
        read_water_balance,
    )
    from hydrolite.ui.state import load_workbench_context

    monkeypatch.setenv("STREAMLIT_CLOUD", "1")
    assert is_streamlit_cloud() is True
    assert read_result_flow(tmp_path / "missing.csv").empty
    subbasin, outlet = read_water_balance(tmp_path / "missing.xlsx")
    assert subbasin.empty
    assert outlet.empty
    assert read_swmm_outputs(tmp_path / "missing") == {}
    assert read_comparison_outputs(tmp_path) == {}
    assert read_validation_outputs(tmp_path) == {}
    assert read_project_validation_outputs(tmp_path) == {}
    context = load_workbench_context(tmp_path / "missing_project")
    assert context.project_loaded is False
    assert "project.yaml not found" in context.error_message


def test_ui_checks_do_not_modify_data_raw():
    before = _snapshot_data_raw()
    from hydrolite.ui.app import scan_case_files

    scan_case_files(Path("cases"))
    after = _snapshot_data_raw()
    assert after == before


def test_no_secrets_or_model_weights_tracked():
    import subprocess

    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False)
    tracked = completed.stdout.splitlines()
    forbidden_suffixes = (".pt", ".pth", ".ckpt", ".onnx")
    assert not any(path.endswith(forbidden_suffixes) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)
