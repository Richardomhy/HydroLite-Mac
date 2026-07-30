import pandas as pd

from hydrolite.lead_time_validation import generate_forecast_cycles, run_assimilated_forecast_cycle


def test_default_lead_times_and_short_event_skip():
    frame = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=8, freq="h"), "open_loop_flow_cms": range(8), "observed_flow_cms": range(8), "nudging_analysis_flow_cms": range(8)})
    cycles = generate_forecast_cycles(frame)
    assert {row["lead_time_hr"] for row in cycles} <= {1, 3, 6, 12}
    assert run_assimilated_forecast_cycle(frame, cycles[0])["result_type"] == "forecast_from_analysis"
