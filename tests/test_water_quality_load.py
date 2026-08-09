import numpy as np
import pandas as pd

from hydrolite.water_quality_load import align_water_quality_and_flow, calculate_load_from_concentration_flow, validate_load_units


def test_mg_l_times_cms_converts_to_kg_day():
    assert calculate_load_from_concentration_flow([1.0], [1.0]).item() == 86.4
    assert validate_load_units("mg/L", "m3/s")["status"] == "passed"


def test_missing_or_negative_flow_never_uses_concentration_as_load():
    values = calculate_load_from_concentration_flow([1.0, 2.0], [np.nan, -1.0])
    assert np.isnan(values).all()


def test_daily_alignment_marks_missing_flow_unavailable():
    obs = pd.DataFrame({"timestamp": ["2025-01-01", "2025-01-02"], "station_id": ["WQ1", "WQ1"], "variable_id": ["TN", "TN"], "value": [1.0, 2.0], "source": ["lab", "lab"]})
    flow = pd.DataFrame({"timestamp": ["2025-01-01"], "station_id": ["WQ1"], "flow_cms": [1.0], "source": ["gage"]})
    ledger = align_water_quality_and_flow(obs, flow, "daily")
    assert ledger.load_status.tolist() == ["available", "flow_unavailable"]
    assert ledger.alignment_method.eq("daily").all()
