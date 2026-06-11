from pathlib import Path

import pandas as pd

from hydrolite.batch import discover_case_files, run_batch


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_batch_inputs(root: Path) -> None:
    data = root / "data"
    data.mkdir()
    _write_text(
        data / "rainfall.csv",
        """time,rain_mm
2026-01-01 00:00,0
2026-01-01 01:00,15
2026-01-01 02:00,25
2026-01-01 03:00,0
""",
    )
    _write_text(
        data / "subcatchments.csv",
        """id,area_km2,curve_number,lag_hours
S1,2.0,80,1.0
""",
    )
    _write_text(
        data / "reaches.csv",
        """id,from,to,K_hours,X
R1,upper,outlet,1.0,0.2
""",
    )


def _write_case(root: Path, name: str) -> Path:
    path = root / "cases" / f"{name}.yaml"
    _write_text(
        path,
        f"""name: {name}

model:
  time_step_hours: 1.0

inputs:
  directory: data
  rainfall: rainfall.csv
  subcatchments: subcatchments.csv
  reaches: reaches.csv

outputs:
  directory: output/{name}
""",
    )
    return path


def test_batch_discovers_yaml_and_yml_files(tmp_path: Path):
    cases = tmp_path / "cases"
    _write_text(cases / "a.yaml", "name: a\n")
    _write_text(cases / "b.yml", "name: b\n")
    _write_text(cases / "ignore.txt", "name: ignore\n")

    found = [path.name for path in discover_case_files(cases)]
    assert found == ["a.yaml", "b.yml"]


def test_batch_summary_marks_success_and_failed_cases(tmp_path: Path):
    _write_batch_inputs(tmp_path)
    _write_case(tmp_path, "ok_case")
    _write_text(
        tmp_path / "cases" / "bad_case.yaml",
        """name: bad_case
model:
  time_step_hours: 1.0
outputs:
  directory: output/bad_case
""",
    )

    summary_path, rows, failed_cases = run_batch(tmp_path / "cases")

    assert summary_path.exists()
    assert len(failed_cases) == 1
    assert {row["status"] for row in rows} == {"success", "failed"}

    summary = pd.read_excel(summary_path)
    assert set(summary["status"]) == {"success", "failed"}
    assert "batch_summary.xlsx" in str(summary_path)


def test_batch_run_does_not_modify_data_raw():
    root = Path("data_raw")
    before = {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    } if root.exists() else {}

    run_batch(Path("cases"))

    after = {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    } if root.exists() else {}
    assert after == before

