import pandas as pd

from hydrolite.water_quality_observations import detect_detection_limit_records, detect_stale_station, run_observation_qc


def _rows():
    return pd.DataFrame([
        {"timestamp": "2025-01-01", "station_id": "WQ1", "variable_id": "TN", "value": 1.0, "unit": "mg/L"},
        {"timestamp": "2025-01-01", "station_id": "WQ1", "variable_id": "TN", "value": 1.0, "unit": "mg/L"},
        {"timestamp": "2025-01-02", "station_id": "WQ1", "variable_id": "TN", "value": -1.0, "unit": "mg/L"},
        {"timestamp": "2025-01-03", "station_id": "WQ1", "variable_id": "TN", "value": None, "unit": "mg/L"},
        {"timestamp": "2025-01-04", "station_id": "WQ1", "variable_id": "TN", "value": 1.0, "unit": "ug/L"},
        {"timestamp": "2025-01-05", "station_id": "WQ1", "variable_id": "TN", "value": None, "unit": "mg/L", "qualifier": "below_detection_limit", "detection_limit": 0.01},
    ])


def test_qc_flags_invalid_duplicate_missing_unit_and_detection_limit():
    qc, _ = run_observation_qc(_rows())
    assert {"duplicate", "invalid", "missing", "unit_error", "below_detection_limit"}.issubset(set(qc.quality_status))
    assert not qc.loc[qc.quality_status.isin(["invalid", "missing", "unit_error", "duplicate"]), "training_eligible"].any()


def test_non_detect_default_preserves_qualifier():
    qc, _ = run_observation_qc(_rows())
    record = qc[qc.below_detection_limit].iloc[0]
    assert pd.isna(record.value)
    assert record.non_detect_method == "preserve_qualifier"
    assert len(detect_detection_limit_records(_rows())) == 1


def test_stale_station_is_reported_not_deleted():
    stale = detect_stale_station(_rows().iloc[:1], stale_days=30, reference_time="2025-03-15")
    assert stale.iloc[0].quality_status == "stale"
