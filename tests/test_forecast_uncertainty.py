import pandas as pd


def _ensemble():
    rows = []
    for member, scale in [("a", 1.0), ("b", 2.0), ("c", 3.0)]:
        for hour in range(3):
            rows.append({"member_id": member, "valid_time": pd.Timestamp("2026-01-01") + pd.Timedelta(hours=hour), "issue_time": pd.Timestamp("2026-01-01"), "interval_minutes": 60, "outlet_flow_cms": scale * hour, "run_status": "success"})
    return pd.DataFrame(rows)


def test_quantiles_peaks_volume_and_threshold_fraction():
    from hydrolite.forecast_uncertainty import calculate_ensemble_quantiles, calculate_exceedance_probability, calculate_peak_distribution, calculate_volume_distribution

    data = _ensemble()
    assert {"p05", "p50", "p95"} <= set(calculate_ensemble_quantiles(data))
    assert calculate_peak_distribution(data).loc[0, "p50"] == 4
    assert calculate_volume_distribution(data).loc[0, "p50"] > 0
    threshold = calculate_exceedance_probability(data, [{"name": "demo", "threshold": 4, "source": "diagnostic_demo_threshold"}])
    assert threshold.loc[0, "scenario_member_exceedance_fraction"] == 2 / 3
