from __future__ import annotations

from pathlib import Path

import pandas as pd


def _rainfall() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-06-01 00:00", "2026-06-01 01:00"]),
            "precipitation_increment_mm": [1.0, 2.0],
        }
    )


def test_dss_backend_diagnosis_and_write_script(tmp_path: Path):
    from hydrolite.hec_hms_precipitation import (
        build_dss_precipitation_write_script,
        detect_hec_dss_write_backends,
        write_dss_backend_diagnosis,
    )

    assert {row["backend"] for row in detect_hec_dss_write_backends()} >= {"hec_hms_java", "hec_dssvue", "python"}
    outputs = write_dss_backend_diagnosis(tmp_path / "diagnosis")
    assert all(path.exists() for path in outputs.values())
    script = build_dss_precipitation_write_script(_rainfall(), tmp_path / "rain.dss", "/P/G/PRECIP-INC//1HOUR/OBS/", tmp_path / "write.py")
    text = script.read_text(encoding="ascii")
    assert "HecDss.open" in text
    assert "TimeSeriesContainer" in text
    assert "PER-CUM" in text


def test_dss_unavailable_is_graceful(monkeypatch, tmp_path: Path):
    import hydrolite.hec_hms_precipitation as precipitation

    monkeypatch.setattr(precipitation, "recommend_hec_dss_write_backend", lambda: {"backend": "unavailable", "status": "unavailable"})
    result = precipitation.write_precipitation_to_dss(
        _rainfall(), tmp_path / "rain.dss", "/P/G/PRECIP-INC//1HOUR/OBS/"
    )
    assert result["status"] == "dss_backend_unavailable"
    assert not (tmp_path / "rain.dss").exists()


def test_precipitation_readback_validation_with_mock(monkeypatch):
    import hydrolite.hec_hms_precipitation as precipitation

    monkeypatch.setattr(
        precipitation,
        "read_back_precipitation_dss_record",
        lambda *_: {
            "status": "success",
            "record_exists": True,
            "record_count": 2,
            "start": "1 June 2026, 00:00",
            "end": "1 June 2026, 01:00",
            "interval_minutes": 60,
            "units": "MM",
            "type": "PER-CUM",
            "values": [1.0, 2.0],
            "missing_values": 0,
        },
    )
    result = precipitation.validate_precipitation_dss_record("unused.dss", "/P/G/PRECIP-INC//1HOUR/OBS/", _rainfall())
    assert result["status"] == "passed"
    assert all(result["checks"].values())


def test_compute_safety_gate_skips_without_ready_rainfall(tmp_path: Path):
    from hydrolite.hec_hms_precipitation import run_hms_rainfall_compute

    result = run_hms_rainfall_compute(tmp_path)
    assert result["compute_executed"] is False
    assert result["status"] in {"dss_backend_unavailable", "gate_failed"}
