from pathlib import Path

import pandas as pd

from hydrolite.runner import run_case


def test_demo_case_runs_and_writes_outputs():
    outputs = run_case(Path("cases/demo.yaml"))
    assert outputs.result_flow_csv.exists()
    assert outputs.summary_xlsx.exists()
    assert outputs.hydrograph_png.exists()
    assert outputs.water_balance_xlsx.exists()
    assert outputs.log_file.exists()

    result = pd.read_csv(outputs.result_flow_csv)
    assert {"time", "inflow_cms", "outflow_cms"}.issubset(result.columns)
    assert result["outflow_cms"].max() > 0


def test_water_balance_workbook_has_expected_sheets_and_fields():
    outputs = run_case(Path("cases/demo.yaml"))
    workbook = pd.ExcelFile(outputs.water_balance_xlsx)
    assert set(workbook.sheet_names) == {"subbasin_balance", "outlet_balance"}

    subbasin = pd.read_excel(outputs.water_balance_xlsx, sheet_name="subbasin_balance")
    outlet = pd.read_excel(outputs.water_balance_xlsx, sheet_name="outlet_balance")
    assert "balance_error_percent" in subbasin.columns
    assert "balance_error_percent" in outlet.columns
