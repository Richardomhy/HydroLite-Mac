import pandas as pd

from hydrolite.hydrologic_observation_qc import detect_flatline_periods, detect_sensor_spikes, validate_rainfall_observations


def test_observation_qc_flags_negative_spike_and_flatline():
    frame = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=9, freq="h"), "rainfall_mm": [0, 0, 0, 0, 0, 0, 100, -1, 0]})
    assert validate_rainfall_observations(frame)["status"] == "rejected"
    spike_frame = frame.copy()
    spike_frame["rainfall_mm"] = [0, 1, 3, 4, 6, 50, 7, 9, 10]
    assert not detect_sensor_spikes(spike_frame, "rainfall_mm", 2).empty
    assert not detect_flatline_periods(frame, "rainfall_mm", 4).empty
