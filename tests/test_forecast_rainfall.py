from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_scenarios_and_seeded_ensemble_are_nonnegative(tmp_path: Path):
    from hydrolite.forecast_rainfall import (
        create_design_storm_scenario,
        create_multiplicative_scenarios,
        generate_stochastic_rainfall_ensemble,
        load_forecast_rainfall,
        validate_rainfall_ensemble,
        write_rainfall_ensemble,
    )

    base = load_forecast_rainfall(ROOT / "data_demo/flood_forecast/demo_rainfall_forecast.csv")
    scaled = create_multiplicative_scenarios(base, [0.8, 1.2])
    first = generate_stochastic_rainfall_ensemble(base, 3, {}, seed=42)
    second = generate_stochastic_rainfall_ensemble(base, 3, {}, seed=42)
    pd.testing.assert_frame_equal(first, second)
    assert (scaled["precipitation_mm"] >= 0).all()
    assert abs(create_design_storm_scenario(60, 6, "center_loaded")["precipitation_mm"].sum() - 60) < 1e-9
    assert validate_rainfall_ensemble(first)["status"] == "passed"
    assert write_rainfall_ensemble(tmp_path, first)["summary"].exists()
