from pathlib import Path

import pandas as pd

from hydrolite.config import load_case
from hydrolite.runner import run_case
from hydrolite.swmm.runner import SWMM_SUMMARY_COLUMNS, read_swmm_summary


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
    assert working.read_bytes() == before
    assert outputs.swmm_summary_xlsx == Path("output/demo_swmm/swmm/swmm_summary.xlsx").resolve()


def test_swmm_summary_fields_are_complete():
    outputs = run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))
    assert outputs.swmm_summary_xlsx is not None
    assert outputs.swmm_summary_xlsx.exists()

    summary = read_swmm_summary(outputs.swmm_summary_xlsx)
    assert list(summary.columns) == SWMM_SUMMARY_COLUMNS
    assert summary.loc[0, "run_status"] in {"success", "skipped", "failed"}


def test_non_swmm_flow_still_works_after_swmm_case():
    run_case(Path("cases/demo_swmm.yaml"), output_dir=Path("output/demo_swmm"))
    outputs = run_case(Path("cases/demo.yaml"), output_dir=Path("output/demo"))
    result = pd.read_csv(outputs.result_flow_csv)
    assert result["outflow_cms"].max() > 0

