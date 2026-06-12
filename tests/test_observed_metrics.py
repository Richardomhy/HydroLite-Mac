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


def test_demo_observed_streamflow_exists_and_fields():
    path = Path("data_demo/observed/demo_observed_streamflow.csv")
    assert path.exists()
    df = pd.read_csv(path)
    assert {"datetime", "gauge_id", "observed_streamflow_m3s"}.issubset(df.columns)
    assert (pd.to_numeric(df["observed_streamflow_m3s"], errors="coerce") >= 0).all()


def test_metrics_functions_run():
    from hydrolite.metrics import kge, mae, nse, pbias, r2, rmse

    observed = [1.0, 2.0, 3.0, 4.0]
    simulated = [1.1, 1.9, 3.2, 3.8]
    for fn in (nse, rmse, mae, pbias, r2, kge):
        value = fn(observed, simulated)
        assert not pd.isna(value)


def test_observed_module_imports_and_negative_validation():
    from hydrolite.observed import load_observed_streamflow, validate_observed_streamflow

    df = load_observed_streamflow("data_demo/observed/demo_observed_streamflow.csv")
    checks, _warnings = validate_observed_streamflow(df)
    assert (checks["status"] != "failed").all()
    bad = df.copy()
    bad.loc[0, "observed_streamflow_m3s"] = -1
    checks, _warnings = validate_observed_streamflow(bad)
    assert "observed_streamflow_non_negative" in set(checks[checks["status"] == "failed"]["check_name"])


def test_negative_observed_flow_makes_validate_fail(tmp_path):
    before = _snapshot_data_raw()
    observed = tmp_path / "bad_observed.csv"
    observed.write_text("datetime,gauge_id,observed_streamflow_m3s\n2024-06-01,G,-1\n", encoding="utf-8")
    base = yaml.safe_load(Path("cases/demo_gee.yaml").read_text(encoding="utf-8"))
    base["observed"]["observed_streamflow_csv"] = str(observed)
    case = tmp_path / "bad_case.yaml"
    case.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-m", "hydrolite", "validate", str(case)], capture_output=True, text=True, check=False, timeout=60)
    assert completed.returncode != 0
    assert _snapshot_data_raw() == before


def test_demo_gee_run_writes_model_performance_outputs():
    before = _snapshot_data_raw()
    completed = subprocess.run([sys.executable, "-m", "hydrolite", "run", "cases/demo_gee.yaml"], capture_output=True, text=True, check=False, timeout=120)
    assert completed.returncode == 0, completed.stderr
    root = Path("output/demo_gee")
    for name in ("observed_vs_simulated.csv", "model_performance.xlsx", "model_performance_report.md", "observed_vs_simulated.png"):
        assert (root / name).exists(), name
    aligned = pd.read_csv(root / "observed_vs_simulated.csv")
    assert {"datetime", "gauge_id", "observed_streamflow_m3s", "simulated_streamflow_m3s"}.issubset(aligned.columns)
    metrics = pd.read_excel(root / "model_performance.xlsx", sheet_name="metrics")
    assert {"NSE", "RMSE", "MAE", "PBIAS", "R2", "KGE", "n_pairs"}.issubset(metrics.columns)
    assert _snapshot_data_raw() == before


def test_openhydronet_prepare_inputs_includes_observed_streamflow():
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "openhydronet", "prepare-inputs", "configs/openhydronet.example.yaml"],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr
    root = Path("output/openhydronet/inputs")
    observed = root / "observed_streamflow.csv"
    assert observed.exists()
    df = pd.read_csv(observed)
    assert {"datetime", "basin_id", "gauge_id", "observed_streamflow_m3s", "source"}.issubset(df.columns)
    warnings = pd.read_excel(root / "input_quality_report.xlsx", sheet_name="warnings")
    names = set(warnings["warning_name"]) if "warning_name" in warnings.columns else set()
    assert "observed_streamflow_missing" not in names


def test_compare_outputs_performance_metrics_sheet():
    completed = subprocess.run([sys.executable, "-m", "hydrolite", "compare", "output/"], capture_output=True, text=True, check=False, timeout=120)
    assert completed.returncode == 0, completed.stderr
    xlsx = Path("output/comparison/scenario_comparison.xlsx")
    workbook = pd.ExcelFile(xlsx)
    assert "performance_metrics" in workbook.sheet_names
    df = pd.read_excel(xlsx, sheet_name="performance_metrics")
    assert {"case_name", "NSE", "RMSE", "MAE", "PBIAS", "R2", "KGE", "n_pairs", "model_performance_file"}.issubset(df.columns)


def test_streamlit_observed_helpers_import():
    from hydrolite.ui.app import load_existing_outputs, read_comparison_outputs

    outputs = load_existing_outputs(Path("output/demo_gee"))
    assert isinstance(outputs, dict)
    comparison = read_comparison_outputs()
    assert isinstance(comparison, dict)
