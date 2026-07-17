from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def _rainfall() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-06-01 00:00", "2026-06-01 01:00", "2026-06-01 02:00"]),
            "precipitation_increment_mm": [0.0, 5.0, 2.0],
        }
    )


def _raw_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "data_raw").rglob("*"))
        if path.is_file()
    }


def test_rainfall_loading_interval_validation_and_normalization(tmp_path: Path):
    from hydrolite.hec_hms_precipitation import (
        infer_precipitation_interval,
        load_hydrolite_rainfall_csv,
        normalize_hms_precipitation_timeseries,
        validate_precipitation_timeseries,
    )

    path = tmp_path / "rainfall.csv"
    path.write_text("time,rainfall_mm\n2026-06-01 00:00,0\n2026-06-01 01:00,5\n2026-06-01 02:00,2\n", encoding="utf-8")
    frame = load_hydrolite_rainfall_csv(path)
    assert list(frame.columns) == ["timestamp", "precipitation_increment_mm"]
    assert infer_precipitation_interval(frame)["interval_minutes"] == 60
    assert validate_precipitation_timeseries(frame)["status"] == "passed"
    normalized, report = normalize_hms_precipitation_timeseries(frame)
    assert len(normalized) == 3
    assert report["normalized_total_mm"] == 7.0


def test_irregular_rainfall_resampling_preserves_total_and_control_alignment():
    from hydrolite.hec_hms_precipitation import align_precipitation_to_control_window, normalize_hms_precipitation_timeseries

    irregular = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-06-01 00:00", "2026-06-01 00:30", "2026-06-01 02:00"]),
            "precipitation_increment_mm": [1.0, 2.0, 4.0],
        }
    )
    normalized, report = normalize_hms_precipitation_timeseries(irregular, interval_minutes=60)
    assert report["resampled"] is True
    assert report["total_difference_mm"] == 0.0
    aligned, alignment = align_precipitation_to_control_window(normalized, "2026-06-01 00:00", "2026-06-01 03:00", 60)
    assert alignment["status"] == "passed"
    assert alignment["tail_zero_fill_applied"] is True
    assert aligned["precipitation_increment_mm"].sum() == 7.0


def test_pathname_gage_mapping_and_catalog_classification(tmp_path: Path):
    from hydrolite.hec_hms_precipitation import (
        build_precipitation_dss_pathname,
        build_precipitation_gage_definition,
        classify_hms_dss_pathnames,
        find_hms_flow_pathnames,
    )

    pathname = build_precipitation_dss_pathname("HydroLite HMS Project", "HydroLite Precip", 60)
    assert pathname == "/HYDROLITE_HMS_PROJECT/HYDROLITE_PRECIP/PRECIP-INC//1HOUR/OBS/"
    definition = build_precipitation_gage_definition("HydroLite_HMS_Project", "HydroLite_Precip", "data/rain.dss", pathname)
    assert "Data Source Type: External DSS" in definition
    assert "Filename: data/rain.dss" in definition
    catalog = [pathname, "/PROJECT/S1/FLOW//1HOUR/RUN/"]
    classified = classify_hms_dss_pathnames(catalog)
    assert classified[0]["category"] == "precipitation_input"
    assert find_hms_flow_pathnames(catalog) == [catalog[1]]


def test_precipitation_gage_meteorology_and_subbasins(tmp_path: Path):
    from hydrolite.hec_hms_precipitation import (
        generate_hms_precipitation_gage,
        link_precipitation_gage_to_meteorologic_model,
        link_meteorologic_model_to_subbasins,
    )

    root = tmp_path / "hms"
    root.mkdir()
    (root / "basin.basin").write_text("Basin: b\nEnd:\n\nSubbasin: S1\nEnd:\n\nSubbasin: S2\nEnd:\n", encoding="utf-8")
    (root / "model.met").write_text("Meteorology: m\n     Precipitation Method: None\nEnd:\n", encoding="utf-8")
    pathname = "/P/G/PRECIP-INC//1HOUR/OBS/"
    generate_hms_precipitation_gage(root, "HydroLite_Precip", "data/rain.dss", pathname, _rainfall())
    link_precipitation_gage_to_meteorologic_model(root, "HydroLite_Precip")
    linkage = link_meteorologic_model_to_subbasins(root)
    assert linkage["unmapped_subbasins"] == []
    text = (root / "model.met").read_text(encoding="utf-8")
    assert text.count("Volume Weight: 1") == 2


def test_rainfall_gate_gracefully_fails_without_backend(tmp_path: Path):
    from hydrolite.hec_hms_precipitation import evaluate_hms_rainfall_gate

    result = evaluate_hms_rainfall_gate(tmp_path)
    assert result["status"] == "failed"
    assert result["rainfall_ready"] is False
    assert "dss_backend_available" in result["failed_checks"]


def test_rainfall_cli_routes(monkeypatch, tmp_path: Path):
    import hydrolite.__main__ as cli

    monkeypatch.setattr(cli, "write_dss_backend_diagnosis", lambda: {"json": tmp_path / "d.json", "markdown": tmp_path / "d.md"})
    monkeypatch.setattr(cli, "create_hms_rainfall_verified_project", lambda *_: {"status": "ready_for_open_probe"})
    monkeypatch.setattr(cli, "evaluate_hms_rainfall_gate", lambda *_: {"status": "passed", "checks": {}, "rainfall_ready": True})
    monkeypatch.setattr(cli, "write_hms_rainfall_gate_report", lambda *_: {})
    monkeypatch.setattr(cli, "run_hms_rainfall_compute", lambda *_args, **_kwargs: {"status": "compute_completed"})
    monkeypatch.setattr(cli, "write_hms_result_catalog_report", lambda *_: {"json": tmp_path / "catalog.json"})
    assert cli.main(["hms", "dss-backends"]) == 0
    assert cli.main(["hms", "create-rainfall-project", "source", "target"]) == 0
    assert cli.main(["hms", "rainfall-gate", "target"]) == 0
    assert cli.main(["hms", "rainfall-compute", "target"]) == 0
    assert cli.main(["hms", "result-catalog", "target"]) == 0


def test_ui_docs_and_data_raw_safety():
    before = _raw_hashes()
    import hydrolite.ui.pages.hec_hms as page

    assert callable(page.render)
    assert (ROOT / "docs" / "hec_hms_precipitation_dss.md").exists()
    assert (ROOT / "docs" / "hec_hms_rainfall_compute_validation.md").exists()
    assert _raw_hashes() == before
