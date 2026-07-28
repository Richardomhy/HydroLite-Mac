from __future__ import annotations

from pathlib import Path

import pandas as pd

from hydrolite.calibration import (
    MAX_CANDIDATES,
    build_parameter_bounds,
    create_calibrated_case,
    generate_multivariate_parameter_sets,
    generate_oat_parameter_sets,
    run_parameter_search,
    select_calibration_target,
    write_parameter_outputs,
)
from hydrolite.hydrology import scs_cn_runoff_depth_mm


def _project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    (project / "cases").mkdir(parents=True)
    (project / "data").mkdir()
    pd.DataFrame({"time": pd.date_range("2026-01-01", periods=6, freq="h"), "rain_mm": [0, 5, 15, 5, 0, 0]}).to_csv(project / "data" / "rainfall.csv", index=False)
    pd.DataFrame({"subbasin_id": ["S1"], "area_km2": [2.0], "cn": [75.0], "initial_abstraction_ratio": [.2], "lag_time_hr": [1.0]}).to_csv(project / "data" / "subbasins.csv", index=False)
    pd.DataFrame({"reach_id": ["R1"], "upstream_reach_id": ["N1"], "downstream_reach_id": ["N2"], "length_km": [1], "slope": [.01], "muskingum_k_hr": [1.0], "muskingum_x": [.2]}).to_csv(project / "data" / "reaches.csv", index=False)
    (project / "project.yaml").write_text("project_name: test\npaths:\n  cases_dir: cases\n  data_dir: data\n  output_dir: output\n  reports_dir: reports\n  configs_dir: configs\n  logs_dir: logs\n", encoding="utf-8")
    case = project / "cases" / "demo.yaml"
    case.write_text("name: demo\nmodel:\n  time_step_hours: 1\ninputs:\n  directory: data\n  rainfall: rainfall.csv\n  subcatchments: subbasins.csv\n  reaches: reaches.csv\noutputs:\n  directory: output/demo\n", encoding="utf-8")
    hms = tmp_path / "hms"
    hms.mkdir()
    pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=6, freq="h"), "flow_cms": [0, 1, 4, 2, 0, 0]}).to_csv(hms / "hec_hms_outlet_timeseries.csv", index=False)
    return project, hms


def test_hms_target_bounds_and_deterministic_search(tmp_path: Path) -> None:
    project, hms = _project(tmp_path)
    target = select_calibration_target(project, hms_comparison_dir=hms)
    assert target["target_mode"] == "hms_cross_model_alignment"
    assert target["terminology_to_use"] == "cross-model alignment"
    _, bounds = write_parameter_outputs(project, tmp_path / "calibration")
    assert {"cn", "muskingum_x"}.issubset(set(bounds["parameter"]))
    assert bounds.loc[bounds["parameter"] == "cn", "lower_bound"].min() >= 30
    first = generate_multivariate_parameter_sets({}, bounds, 4, seed=42)
    assert first == generate_multivariate_parameter_sets({}, bounds, 4, seed=42)
    assert len(first) == 4 and len(generate_oat_parameter_sets({}, bounds)) >= 2
    assert scs_cn_runoff_depth_mm(60, 75, .1) > scs_cn_runoff_depth_mm(60, 75, .3)


def test_search_is_bounded_and_creates_non_overwriting_case(tmp_path: Path) -> None:
    project, hms = _project(tmp_path)
    target = select_calibration_target(project, hms_comparison_dir=hms)
    bounds = build_parameter_bounds(project)
    result = run_parameter_search(project, target, bounds, tmp_path / "calibration" / "search", max_candidates=3)
    assert len(result["results"]) <= MAX_CANDIDATES
    assert not result["ranked"].empty
    generated = create_calibrated_case(project, result["best"], project / "cases" / "demo_aligned.yaml")
    assert generated["case"].exists() and (project / "cases" / "demo.yaml").exists()


def test_candidate_uses_alignment_score_for_hms_target(tmp_path: Path) -> None:
    project, hms = _project(tmp_path)
    target = select_calibration_target(project, hms_comparison_dir=hms)
    result = run_parameter_search(project, target, build_parameter_bounds(project), tmp_path / "search", max_candidates=1)
    row = result["results"].iloc[0]
    assert row["alignment_score"] == row["objective_score"]


def test_search_rejects_more_than_forty_candidates(tmp_path: Path) -> None:
    project, _ = _project(tmp_path)
    bounds = build_parameter_bounds(project)
    try:
        generate_multivariate_parameter_sets({}, bounds, MAX_CANDIDATES + 1)
    except ValueError as exc:
        assert "must not exceed" in str(exc)
    else:
        raise AssertionError("candidate cap must be enforced")
