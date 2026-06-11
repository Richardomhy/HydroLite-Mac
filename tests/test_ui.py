from pathlib import Path

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
    import hydrolite.ui.app as app

    assert app.PROJECT_ROOT.exists()


def test_ui_case_scan_finds_demo_cases():
    from hydrolite.ui.app import scan_case_files

    names = {path.name for path in scan_case_files(Path("cases"))}
    assert "demo.yaml" in names
    assert "demo_variant.yaml" in names


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


def test_ui_checks_do_not_modify_data_raw():
    before = _snapshot_data_raw()
    from hydrolite.ui.app import scan_case_files

    scan_case_files(Path("cases"))
    after = _snapshot_data_raw()
    assert after == before
