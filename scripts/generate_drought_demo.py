#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data_demo" / "drought"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2000-01-01", "2019-12-31", freq="D")
    rng = np.random.default_rng(20260730)
    rows = []
    basin_rain = np.zeros(len(dates))
    temperature = np.zeros(len(dates))
    for position, date in enumerate(dates):
        seasonal = np.sin(2 * np.pi * (date.dayofyear - 170) / 365.25)
        tmean = 21.5 + 7.5 * seasonal + rng.normal(0, 1.2)
        temperature[position] = tmean
        wet_probability = 0.18 + 0.23 * max(seasonal, -0.4)
        rainfall = rng.gamma(1.6, 7.0) if rng.random() < wet_probability else 0.0
        if pd.Timestamp("2002-06-01") <= date <= pd.Timestamp("2004-03-31"):
            rainfall *= 0.48
        if pd.Timestamp("2009-04-01") <= date <= pd.Timestamp("2011-02-28"):
            rainfall *= 0.55
        if pd.Timestamp("2015-05-01") <= date <= pd.Timestamp("2016-12-31"):
            rainfall *= 0.40
        basin_rain[position] = rainfall
        for subbasin_id, multiplier in (("SB1", 0.92), ("SB2", 1.08)):
            rows.append({
                "date": date.date().isoformat(),
                "subbasin_id": subbasin_id,
                "precipitation_mm": round(max(rainfall * multiplier + rng.normal(0, 0.12), 0.0), 3),
                "temperature_min_c": round(tmean - 4.5, 3),
                "temperature_max_c": round(tmean + 4.5, 3),
                "temperature_mean_c": round(tmean, 3),
                "quality_status": "synthetic_demo",
                "source": "HydroLite deterministic synthetic generator",
                "synthetic_demo": True,
            })
    meteorology = pd.DataFrame(rows)
    meteorology.to_csv(OUTPUT / "daily_meteorology.csv", index=False)

    wet_memory = pd.Series(basin_rain).rolling(45, min_periods=1).mean().to_numpy()
    dry_memory = pd.Series(basin_rain).rolling(180, min_periods=1).sum().to_numpy()
    flow = np.maximum(0.02 + wet_memory * 0.055 + dry_memory * 0.0007 + rng.normal(0, 0.01, len(dates)), 0)
    pd.DataFrame({
        "date": dates.date.astype(str), "subbasin_id": "OUTLET", "streamflow_cms": flow.round(5),
        "quality_status": "synthetic_demo", "source": "synthetic lagged rainfall response", "synthetic_demo": True,
    }).to_csv(OUTPUT / "observed_streamflow.csv", index=False)

    soil = np.clip(0.18 + pd.Series(basin_rain).rolling(60, min_periods=1).sum().to_numpy() / 800 + rng.normal(0, 0.008, len(dates)), 0.12, 0.44)
    pd.DataFrame({
        "date": dates.date.astype(str), "subbasin_id": "SB1", "soil_moisture_fraction": soil.round(5),
        "quality_status": "synthetic_demo", "source": "synthetic soil bucket proxy", "synthetic_demo": True,
    }).to_csv(OUTPUT / "observed_soil_moisture.csv", index=False)

    groundwater = np.clip(70 + pd.Series(basin_rain - 2.4).rolling(365, min_periods=1).sum().to_numpy() * 0.025, 20, 180)
    pd.DataFrame({
        "date": dates.date.astype(str), "subbasin_id": "SB1", "groundwater_storage_mm": groundwater.round(4),
        "quality_status": "synthetic_demo", "source": "synthetic conceptual storage", "synthetic_demo": True,
    }).to_csv(OUTPUT / "observed_groundwater.csv", index=False)

    reservoir = np.clip(2_000_000 + pd.Series(flow - 0.15).cumsum().to_numpy() * 86400 * 0.05, 500_000, 4_000_000)
    pd.DataFrame({
        "date": dates.date.astype(str), "reservoir_id": "R1", "storage_m3": reservoir.round(2),
        "stage_m": (90 + reservoir / 1_000_000).round(4),
        "quality_status": "synthetic_demo", "source": "synthetic reservoir response", "synthetic_demo": True,
    }).to_csv(OUTPUT / "observed_reservoir.csv", index=False)

    soil_config = {
        "synthetic_demo": True, "parameter_source": "synthetic_demo_default",
        "soil_depth_mm": 1000, "field_capacity": 0.30, "wilting_point": 0.12,
        "saturation": 0.45, "saturated_hydraulic_conductivity": 45,
        "percolation_coefficient": 0.03, "interflow_coefficient": 0.02,
        "root_depth_mm": 600, "initial_soil_moisture": 0.27,
    }
    (OUTPUT / "land_soil_parameters.yaml").write_text(yaml.safe_dump(soil_config, sort_keys=False), encoding="utf-8")
    continuous = {
        "model": {"name": "HydroLite continuous synthetic demo", "time_step": "daily", "synthetic_demo": True},
        "input": {"daily_meteorology_csv": "daily_meteorology.csv"},
        "output": {"folder": "output/drought_model/continuous"},
        "pet": {"method": "Hargreaves_Samani", "latitude": 22.6, "elevation_m": 55},
        "warmup": {"days": 365, "method": "observed_preceding_period"},
        "routing": {"method": "linear_reservoir", "k_days": 2.5, "x": 0.2, "reach_id": "OUTLET"},
        "reservoir": {"mode": "no_reservoir"},
        "water_balance": {"daily_tolerance_mm": 1e-6, "period_tolerance_mm": 1e-4},
        "parameters": {
            "interception_capacity_mm": 2.0, "surface_storage_capacity_mm": 8.0,
            "upper_soil_capacity_mm": 120.0, "lower_soil_capacity_mm": 260.0,
            "infiltration_capacity_mm_day": 45.0, "infiltration_coefficient": 1.0,
            "upper_field_capacity_fraction": 0.65, "lower_field_capacity_fraction": 0.70,
            "percolation_coefficient": 0.04, "groundwater_recharge_coefficient": 0.025,
            "interflow_coefficient": 0.025, "baseflow_coefficient": 0.012,
            "deep_loss_coefficient": 0.001, "et_coefficient": 1.0,
            "initial_upper_soil_fraction": 0.60, "initial_lower_soil_fraction": 0.70,
            "initial_groundwater_storage_mm": 80.0, "initial_channel_storage_m3": 0.0,
        },
        "subbasins": [
            {"subbasin_id": "SB1", "area_km2": 62.0, "parameter_source": "synthetic_demo_default"},
            {"subbasin_id": "SB2", "area_km2": 48.0, "parameter_source": "synthetic_demo_default"},
        ],
    }
    (OUTPUT / "continuous_model_config.yaml").write_text(yaml.safe_dump(continuous, sort_keys=False), encoding="utf-8")
    (OUTPUT / "drought_index_config.yaml").write_text(yaml.safe_dump({
        "synthetic_demo": True, "baseline_period": ["2000-01-01", "2014-12-31"],
        "scales_months": [1, 3, 6, 12, 24], "distributions": {"SPI": "gamma", "SPEI": "normal", "SSI": "gamma"},
        "classification_source": "diagnostic_default_thresholds",
    }, sort_keys=False), encoding="utf-8")
    (OUTPUT / "drought_forecast_config.yaml").write_text(yaml.safe_dump({
        "mode": "scenario_simulation", "synthetic_demo": True, "analysis_date": "2018-12-31",
        "lead_months": [1, 3, 6, 12], "maximum_members": 10,
        "continuous_model_config": "continuous_model_config.yaml",
        "uncertainty_sources": ["climate_forcing", "initial_soil_state", "model_parameters", "PET_method", "data_quality"],
    }, sort_keys=False), encoding="utf-8")
    pd.DataFrame([
        {"scenario_id":"baseline","scenario_type":"synthetic_demo","precipitation_scale":1.0,"temperature_offset_c":0.0,"pet_scale":1.0},
        {"scenario_id":"precip_80","scenario_type":"user_scenario","precipitation_scale":0.8,"temperature_offset_c":0.0,"pet_scale":1.0},
        {"scenario_id":"precip_60","scenario_type":"user_scenario","precipitation_scale":0.6,"temperature_offset_c":0.0,"pet_scale":1.0},
        {"scenario_id":"temperature_plus_1","scenario_type":"user_scenario","precipitation_scale":1.0,"temperature_offset_c":1.0,"pet_scale":1.0},
        {"scenario_id":"temperature_plus_2","scenario_type":"user_scenario","precipitation_scale":1.0,"temperature_offset_c":2.0,"pet_scale":1.0},
        {"scenario_id":"pet_plus_15","scenario_type":"user_scenario","precipitation_scale":1.0,"temperature_offset_c":0.0,"pet_scale":1.15},
        {"scenario_id":"delayed_rainfall","scenario_type":"user_scenario","precipitation_scale":1.0,"temperature_offset_c":0.0,"pet_scale":1.0},
        {"scenario_id":"dry_historical_analogue","scenario_type":"synthetic_demo","precipitation_scale":0.5,"temperature_offset_c":1.0,"pet_scale":1.10},
    ]).to_csv(OUTPUT / "climate_scenarios.csv", index=False)
    (OUTPUT / "expected_results.json").write_text(json.dumps({
        "synthetic_demo": True, "start_date": "2000-01-01", "end_date": "2019-12-31",
        "record_days": len(dates), "subbasin_count": 2, "minimum_drought_events": 3,
        "truthfulness": "Workflow verification only; not observed climate or operational drought warning.",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
