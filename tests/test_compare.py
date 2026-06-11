from pathlib import Path
import subprocess
import sys

import pandas as pd

from hydrolite.compare import run_compare
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


def test_compare_cli_generates_required_outputs():
    before = _snapshot_data_raw()
    run_case(Path("cases/demo.yaml"), output_dir=Path("output/demo"))
    run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))

    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "compare", "output/"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    comparison = Path("output/comparison")
    assert (comparison / "scenario_comparison.xlsx").exists()
    assert (comparison / "scenario_comparison.csv").exists()
    assert (comparison / "hydrolite_report.md").exists()
    assert (comparison / "peak_flow_comparison.png").exists()
    assert (comparison / "volume_comparison.png").exists()
    assert (comparison / "water_balance_comparison.png").exists()
    assert (comparison / "swmm_kpi_comparison.png").exists()
    assert _snapshot_data_raw() == before


def test_compare_workbook_sheets_and_fields_are_complete():
    run_compare(Path("output"))
    workbook = Path("output/comparison/scenario_comparison.xlsx")
    sheets = pd.read_excel(workbook, sheet_name=None)

    required = {
        "overview": {
            "case_name",
            "output_folder",
            "has_hydrolite_result",
            "has_water_balance",
            "has_swmm",
            "has_coupling",
            "run_status",
            "notes",
        },
        "hydrology_metrics": {
            "case_name",
            "peak_flow",
            "peak_time",
            "total_runoff_volume_m3",
            "result_flow_csv",
        },
        "water_balance_metrics": {
            "case_name",
            "max_subbasin_balance_error_percent",
            "outlet_balance_error_percent",
            "water_balance_file",
        },
        "swmm_metrics": {
            "case_name",
            "swmm_status",
            "backend_used",
            "max_node_depth",
            "max_link_flow",
            "total_flooding_volume",
            "total_outflow_volume",
            "swmm_summary_file",
            "swmm_kpis_file",
        },
        "coupling_metrics": {
            "case_name",
            "coupling_enabled",
            "coupling_status",
            "target_node",
            "inflow_name",
            "timeseries_points",
            "max_flow",
            "total_inflow_volume_m3",
            "coupling_summary_file",
        },
        "missing_outputs": {"case_name", "expected_file", "status", "message"},
    }

    assert set(required).issubset(sheets)
    for sheet_name, columns in required.items():
        assert columns.issubset(sheets[sheet_name].columns)


def test_compare_handles_missing_case_files(tmp_path: Path):
    case_dir = tmp_path / "partial_case"
    case_dir.mkdir()
    (case_dir / "result_flow.csv").write_text(
        "time,outflow_cms\n2026-01-01 00:00,0\n2026-01-01 01:00,1.5\n",
        encoding="utf-8",
    )

    outputs = run_compare(tmp_path)

    assert outputs.xlsx.exists()
    missing = pd.read_excel(outputs.xlsx, sheet_name="missing_outputs")
    assert not missing.empty
    assert "water_balance.xlsx" in set(missing["expected_file"])


def test_non_swmm_case_is_included_in_comparison():
    run_case(Path("cases/demo.yaml"), output_dir=Path("output/demo"))
    outputs = run_compare(Path("output"))
    overview = pd.read_excel(outputs.xlsx, sheet_name="overview")
    demo = overview[overview["case_name"] == "demo"].iloc[0]
    assert bool(demo["has_hydrolite_result"]) is True
    assert bool(demo["has_swmm"]) is False


def test_streamlit_comparison_reader_imports():
    from hydrolite.ui.app import read_comparison_outputs

    run_compare(Path("output"))
    outputs = read_comparison_outputs(Path("output"))
    assert "overview" in outputs
    assert "scenario_comparison_xlsx" in outputs
