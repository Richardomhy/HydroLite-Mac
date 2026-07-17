from __future__ import annotations

import pandas as pd
import pytest

from hydrolite.flood_metrics import (
    calculate_duration_above_threshold,
    calculate_event_flow_metrics,
    calculate_runoff_volume,
    compare_event_flow_metrics,
)


def _event(values=(0.0, 2.0, 4.0, 2.0, 0.0)) -> pd.DataFrame:
    return pd.DataFrame({"timestamp": pd.date_range("2026-06-01", periods=len(values), freq="1h"), "flow_cms": values})


def test_event_peak_timing_volume_and_limbs():
    metrics = calculate_event_flow_metrics(_event())
    assert metrics["peak_flow_cms"] == 4.0
    assert metrics["peak_time"] == "2026-06-01T02:00:00"
    assert metrics["time_to_peak_hr"] == 2.0
    assert metrics["rising_limb_duration_hr"] == 2.0
    assert metrics["recession_limb_duration_hr"] == 2.0
    assert calculate_runoff_volume(_event()) == pytest.approx(28800.0)


def test_threshold_duration_and_relative_threshold_label():
    assert calculate_duration_above_threshold(_event(), 1.0) == 3.0
    metrics = calculate_event_flow_metrics(_event())
    assert all(row["threshold_type"] == "diagnostic_relative_threshold" for row in metrics["thresholds"])
    assert "statutory" in metrics["threshold_note"]


def test_event_comparison_differences():
    reference = calculate_event_flow_metrics(_event())
    compared = calculate_event_flow_metrics(_event((0.0, 1.0, 2.0, 1.0, 0.0)))
    result = compare_event_flow_metrics(reference, compared)
    assert result["peak_flow_percent_difference"] == -50.0
    assert result["peak_timing_difference_hr"] == 0.0
