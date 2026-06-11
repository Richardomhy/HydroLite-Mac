from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pandas as pd

from hydrolite.batch import run_batch
from hydrolite.runner import run_case
from hydrolite.validate import validate_target


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_valid_project(root: Path, *, rainfall: str | None = None, subbasins: str | None = None, reaches: str | None = None) -> Path:
    _write(
        root / "data" / "rainfall.csv",
        rainfall
        or """time,subbasin_id,rain_mm
2026-01-01 00:00,S1,0
2026-01-01 01:00,S1,5
""",
    )
    _write(
        root / "data" / "subbasins.csv",
        subbasins
        or """id,area_km2,curve_number,lag_hours
S1,1.0,80,1.0
""",
    )
    _write(
        root / "data" / "reaches.csv",
        reaches
        or """id,from,to,K_hours,X
R1,upper,outlet,1.0,0.2
""",
    )
    case = root / "cases" / "case.yaml"
    _write(
        case,
        """name: case
model:
  time_step_hours: 1.0
inputs:
  directory: data
  rainfall: rainfall.csv
  subcatchments: subbasins.csv
  reaches: reaches.csv
outputs:
  directory: output/case
""",
    )
    return case


def test_validate_demo_yaml_cli_passes():
    before = _snapshot_data_raw()
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "validate", "cases/demo.yaml"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert Path("output/validation/validation_summary.xlsx").exists()
    assert Path("output/validation/validation_summary.csv").exists()
    assert Path("output/validation/validation_report.md").exists()
    assert _snapshot_data_raw() == before


def test_validate_demo_swmm_yaml_cli_passes():
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "validate", "cases/demo_swmm.yaml"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr


def test_validate_cases_directory_cli_executes():
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "validate", "cases/"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    overview = pd.read_excel("output/validation/validation_summary.xlsx", sheet_name="overview")
    assert {"demo", "demo_swmm", "demo_variant"}.issubset(set(overview["case_name"]))


def test_validation_workbook_sheets_exist():
    result = validate_target(Path("cases/demo.yaml"))
    sheets = pd.read_excel(result.outputs.xlsx, sheet_name=None)
    assert {"overview", "checks", "errors", "warnings"}.issubset(sheets)
    assert {
        "case_file",
        "case_name",
        "check_group",
        "check_name",
        "status",
        "message",
        "severity",
    }.issubset(sheets["checks"].columns)


def test_missing_required_yaml_field_fails(tmp_path: Path):
    case = tmp_path / "cases" / "bad.yaml"
    _write(case, "name: bad\n")
    result = validate_target(case)
    assert result.has_fatal_errors
    assert "Missing input.rainfall_csv" in " ".join(result.errors["message"].astype(str))


def test_negative_rainfall_fails(tmp_path: Path):
    case = _write_valid_project(
        tmp_path,
        rainfall="""time,subbasin_id,rain_mm
2026-01-01 00:00,S1,-1
""",
    )
    result = validate_target(case)
    assert result.has_fatal_errors
    assert "non-negative" in " ".join(result.errors["message"].astype(str))


def test_invalid_subbasin_area_and_cn_fail(tmp_path: Path):
    case = _write_valid_project(
        tmp_path,
        subbasins="""id,area_km2,curve_number,lag_hours
S1,0,101,1.0
""",
    )
    result = validate_target(case)
    messages = " ".join(result.errors["message"].astype(str))
    assert result.has_fatal_errors
    assert "area_km2 must be > 0" in messages
    assert "0 < cn <= 100" in messages


def test_muskingum_stability_failure_is_fatal(tmp_path: Path):
    case = _write_valid_project(
        tmp_path,
        reaches="""id,from,to,K_hours,X
R1,upper,outlet,2.0,0.4
""",
    )
    result = validate_target(case)
    messages = " ".join(result.errors["message"].astype(str))
    assert result.has_fatal_errors
    assert "reach_id=R1" in messages
    assert "dt=" in messages
    assert "K=" in messages
    assert "X=" in messages


def test_swmm_coupling_missing_source_flow_is_warning_only(tmp_path: Path):
    case = _write_valid_project(tmp_path)
    _write(tmp_path / "data_raw" / "swmm" / "demo.inp", "[TITLE]\nDemo\n")
    case.write_text(
        case.read_text(encoding="utf-8")
        + """
swmm:
  enabled: true
  inp_file: data_raw/swmm/demo.inp
  coupling:
    enabled: true
    source_flow_csv: output/case/result_flow.csv
    source_time_column: time
    source_flow_column: outflow_cms
    target_node: J1
    inflow_name: HYDROLITE_INFLOW
    flow_unit: CMS
""",
        encoding="utf-8",
    )
    result = validate_target(case)
    assert not result.has_fatal_errors
    assert "source_flow_csv not found yet" in " ".join(result.warnings["message"].astype(str))


def test_runner_validates_by_default(monkeypatch):
    called = {"value": False}

    def fake_validate(_target):
        called["value"] = True
        return SimpleNamespace(
            has_fatal_errors=False,
            errors=pd.DataFrame(columns=["message"]),
            warnings=pd.DataFrame(columns=["check_name", "message"]),
            outputs=SimpleNamespace(xlsx=Path("output/validation/validation_summary.xlsx")),
        )

    monkeypatch.setattr("hydrolite.runner.validate_target", fake_validate)
    run_case(Path("cases/demo.yaml"), output_dir=Path("output/demo"))
    assert called["value"] is True


def test_batch_marks_failed_validation(tmp_path: Path):
    _write_valid_project(tmp_path)
    _write(tmp_path / "cases" / "bad.yaml", "name: bad\n")
    summary_path, rows, failed_cases = run_batch(tmp_path / "cases")
    assert summary_path.exists()
    assert failed_cases
    assert any(row["status"] == "failed_validation" for row in rows)
    summary = pd.read_excel(summary_path)
    assert "validation_status" in summary.columns
    assert "validation_message" in summary.columns


def test_streamlit_validation_reader_imports():
    from hydrolite.ui.app import read_validation_outputs

    validate_target(Path("cases/demo.yaml"))
    outputs = read_validation_outputs(Path("output"))
    assert "overview" in outputs
    assert "checks" in outputs
