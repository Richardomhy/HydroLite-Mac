from pathlib import Path
import subprocess
import sys

import pandas as pd

from hydrolite.config import SwmmCouplingConfig
from hydrolite.config import load_case
from hydrolite.runner import run_case
from hydrolite.swmm.runner import SWMM_SUMMARY_COLUMNS, read_swmm_summary, run_swmm


def test_swmm_absent_keeps_existing_case_running():
    config = load_case(Path("cases/demo.yaml"))
    assert config.swmm_enabled is False
    outputs = run_case(Path("cases/demo.yaml"), output_dir=Path("output/demo"))
    assert outputs.result_flow_csv.exists()
    assert outputs.swmm_summary_xlsx is None


def test_demo_swmm_yaml_is_recognized():
    config = load_case(Path("cases/demo_swmm.yaml"))
    assert config.name == "demo_swmm"
    assert config.swmm_enabled is True
    assert config.swmm_inp_file == Path("data_raw/swmm/demo.inp").resolve()


def test_swmm_run_copies_working_inp_and_preserves_original():
    original = Path("data_raw/swmm/demo.inp")
    before = original.read_bytes()

    outputs = run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))

    assert original.read_bytes() == before
    working = Path("output/demo_swmm/swmm/working.inp")
    assert working.exists()
    assert "HYDROLITE_INFLOW" in working.read_text(encoding="utf-8")
    assert outputs.swmm_summary_xlsx == Path("output/demo_swmm/swmm/swmm_summary.xlsx").resolve()


def test_swmm_summary_fields_are_complete():
    outputs = run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))
    assert outputs.swmm_summary_xlsx is not None
    assert outputs.swmm_summary_xlsx.exists()

    summary = read_swmm_summary(outputs.swmm_summary_xlsx)
    assert list(summary.columns) == SWMM_SUMMARY_COLUMNS
    assert summary.loc[0, "run_status"] in {"success", "skipped", "failed"}
    assert "backend_used" in summary.columns
    assert "backend_attempts" in summary.columns
    assert "diagnosis_file" in summary.columns
    assert "external_solver_available" in summary.columns
    assert "external_solver_python" in summary.columns
    assert "external_solver_status" in summary.columns
    assert "external_solver_summary_json" in summary.columns
    assert "solver_env_diagnosis_file" in summary.columns
    assert "node_depth_timeseries_csv" in summary.columns
    assert "link_flow_timeseries_csv" in summary.columns
    assert "system_timeseries_csv" in summary.columns
    assert "swmm_kpis_xlsx" in summary.columns
    assert "coupling_enabled" in summary.columns
    assert "coupling_status" in summary.columns
    assert "coupling_summary_file" in summary.columns
    assert "target_node" in summary.columns
    assert "inflow_name" in summary.columns


def test_non_swmm_flow_still_works_after_swmm_case():
    run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))
    outputs = run_case(Path("cases/demo.yaml"), output_dir=Path("output/demo"))
    result = pd.read_csv(outputs.result_flow_csv)
    assert result["outflow_cms"].max() > 0


def test_swmm_result_tables_exist_with_required_fields():
    outputs = run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))
    swmm_dir = outputs.output_dir / "swmm"

    assert (swmm_dir / "swmm_summary.xlsx").exists()
    assert (swmm_dir / "swmm_kpis.xlsx").exists()
    assert (swmm_dir / "node_depth_timeseries.csv").exists()
    assert (swmm_dir / "link_flow_timeseries.csv").exists()
    assert (swmm_dir / "system_timeseries.csv").exists()

    node_depth = pd.read_csv(swmm_dir / "node_depth_timeseries.csv")
    link_flow = pd.read_csv(swmm_dir / "link_flow_timeseries.csv")
    system = pd.read_csv(swmm_dir / "system_timeseries.csv")
    assert {"datetime", "node_id", "depth"}.issubset(node_depth.columns)
    assert {"datetime", "link_id", "flow"}.issubset(link_flow.columns)
    assert {"datetime", "runoff", "flooding", "outflow", "storage"}.issubset(system.columns)

    kpis = pd.read_excel(swmm_dir / "swmm_kpis.xlsx")
    assert {
        "run_status",
        "backend_used",
        "max_node_depth",
        "max_link_flow",
        "total_flooding_volume",
        "total_outflow_volume",
        "node_count",
        "link_count",
        "report_file",
        "output_file",
    }.issubset(kpis.columns)


def test_swmm_coupling_writes_working_inp_and_summary():
    original = Path("data_raw/swmm/demo.inp")
    before = original.read_bytes()
    outputs = run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))
    swmm_dir = outputs.output_dir / "swmm"

    assert original.read_bytes() == before
    assert "HYDROLITE_INFLOW" in (swmm_dir / "working.inp").read_text(encoding="utf-8")
    coupling_summary = pd.read_excel(swmm_dir / "coupling_summary.xlsx")
    assert {
        "coupling_enabled",
        "coupling_status",
        "source_flow_csv",
        "source_time_column",
        "source_flow_column",
        "target_node",
        "inflow_name",
        "flow_unit",
        "timeseries_points",
        "min_flow",
        "max_flow",
        "total_inflow_volume_m3",
        "working_inp",
        "error_message",
    }.issubset(coupling_summary.columns)
    assert coupling_summary.loc[0, "coupling_status"] == "success"


def test_swmm_coupling_missing_target_node_fails_gracefully(tmp_path: Path):
    source = tmp_path / "flow.csv"
    source.write_text(
        "time,outflow_cms\n2026-01-01 00:00,0\n2026-01-01 01:00,1\n",
        encoding="utf-8",
    )
    result, summary_path = run_swmm(
        inp_file=Path("data_raw/swmm/demo.inp").resolve(),
        case_output_dir=tmp_path / "case",
        result_flow_csv=source,
        coupling=SwmmCouplingConfig(
            enabled=True,
            source_flow_csv=source,
            source_time_column="time",
            source_flow_column="outflow_cms",
            target_node="MISSING_NODE",
            inflow_name="HYDROLITE_INFLOW",
            flow_unit="CMS",
        ),
        logger=__import__("logging").getLogger("test-swmm"),
    )
    assert result.run_status == "failed"
    assert result.coupling_status == "failed"
    assert summary_path.exists()
    coupling_summary = pd.read_excel(tmp_path / "case" / "swmm" / "coupling_summary.xlsx")
    assert "target_node does not exist" in coupling_summary.loc[0, "error_message"]


def test_swmm_diagnosis_script_runs_and_writes_report():
    completed = subprocess.run(
        [sys.executable, "scripts/diagnose_swmm_backend.py"],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0
    report = Path("output/swmm_backend_diagnosis.txt")
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "python_version" in text
    assert "direct_run" in text


def test_external_solver_argument_parser():
    from scripts.swmm_env.run_swmm_solver import build_parser

    args = build_parser().parse_args(
        ["--inp", "a.inp", "--rpt", "a.rpt", "--out", "a.out", "--summary", "a.json"]
    )
    assert args.inp == "a.inp"
    assert args.rpt == "a.rpt"
    assert args.out == "a.out"
    assert args.summary == "a.json"


def test_external_solver_summary_json_structure(tmp_path: Path):
    from scripts.swmm_env.run_swmm_solver import run_solver

    missing_inp = tmp_path / "missing.inp"
    summary = tmp_path / "external_solver_summary.json"
    code, payload = run_solver(
        missing_inp,
        tmp_path / "model.rpt",
        tmp_path / "model.out",
        summary,
    )
    assert code != 0
    assert summary.exists()
    assert {"backend_used", "backend_attempts", "return_code", "error_message"}.issubset(
        payload
    )


def test_swmm_flow_without_external_env_is_graceful(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("HYDROLITE_SWMM_PYTHON", raising=False)
    monkeypatch.setenv("PATH", "")
    outputs = run_case(Path("cases/demo_swmm.yaml"), output_dir=tmp_path / "demo_swmm")
    assert outputs.result_flow_csv.exists()
    assert outputs.swmm_summary_xlsx is not None
    summary = read_swmm_summary(outputs.swmm_summary_xlsx)
    assert "external_solver_available" in summary.columns
