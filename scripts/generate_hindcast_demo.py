#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hydrolite.hydrology import runoff_to_flow_cms
from hydrolite.io import read_reaches, read_subcatchments
from hydrolite.routing import route_reaches


OUTPUT = ROOT / "data_demo" / "hindcast_validation"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = ROOT / "projects" / "qgis_workflow_project" / "data"
    subbasins = read_subcatchments(data / "subbasins.csv")
    reaches = read_reaches(data / "reaches.csv")
    rain_rows, flow_rows, stage_rows, assimilation_rows, event_rows = [], [], [], [], []
    patterns = [
        [2, 6, 12, 20, 14, 7, 2],
        [1, 4, 9, 15, 22, 18, 8, 3],
        [3, 10, 18, 28, 20, 8],
        [1, 3, 8, 16, 25, 30, 18, 7, 2],
        [4, 12, 24, 35, 26, 14, 5],
        [2, 8, 20, 32, 38, 25, 10, 3],
    ]
    for index, pattern in enumerate(patterns, start=1):
        event_id = f"E{index:03d}"
        start = pd.Timestamp("2024-04-01") + pd.Timedelta(days=(index - 1) * 35)
        times = pd.date_range(start, periods=42, freq="h")
        rain = np.zeros(len(times))
        rain[6:6 + len(pattern)] = np.asarray(pattern, dtype=float)
        model_rain = pd.DataFrame({"time": times, "rain_mm": rain})
        routed = route_reaches(runoff_to_flow_cms(model_rain, subbasins, 1.0), reaches, 1.0)
        model = routed.set_index("time")["outflow_cms"].reindex(times, fill_value=0).to_numpy()
        baseflow = 0.25 + index * 0.04
        scale = 0.92 + index * 0.025
        observed = np.maximum(0, model * scale + baseflow * np.exp(-np.arange(len(times)) / 48) + .06 * np.sin(np.arange(len(times)) / 2))
        stage = 100 + observed * .035
        split = "calibration" if index <= 3 else "validation" if index <= 5 else "test"
        active = np.flatnonzero(rain > 0)
        event_rows.append({
            "event_id": event_id, "event_name": f"Synthetic flood {index}", "rainfall_start": times[active[0]],
            "rainfall_end": times[active[-1]], "runoff_start": times[active[0]], "peak_time": times[int(np.argmax(observed))],
            "runoff_end": times[-1], "warmup_start": times[0], "analysis_end": times[-1],
            "duration_hr": len(times) - 1, "antecedent_window_hr": 6, "total_rainfall_mm": float(rain.sum()),
            "maximum_intensity_mm_hr": float(rain.max()), "peak_flow_cms": float(observed.max()),
            "runoff_volume_m3": float(observed.sum() * 3600), "initial_flow_cms": float(observed[0]),
            "initial_stage_m": float(stage[0]), "stations": "RG_DEMO,OUTLET_DEMO", "spatial_coverage": 1.0,
            "temporal_coverage": 1.0, "quality_status": "accepted", "observed_is_synthetic": True,
            "included_for_calibration": split == "calibration", "included_for_validation": split == "validation",
            "included_for_test": split == "test", "exclusion_reason": "", "warnings": "",
            "synthetic_demo": True,
        })
        for position, timestamp in enumerate(times):
            common = {"timestamp": timestamp, "event_id": event_id, "timezone": "Asia/Shanghai", "quality_flag": "synthetic_demo", "source": "original_hydrolite_demo_generator", "synthetic_demo": True}
            rain_rows.append({**common, "station_id": "RG_DEMO", "rainfall_mm": round(float(rain[position]), 4), "unit": "mm", "measurement_method": "synthetic"})
            flow_rows.append({**common, "station_id": "OUTLET_DEMO", "flow_cms": round(float(observed[position]), 6), "unit": "m3/s", "measurement_method": "synthetic", "datum": "", "uncertainty": 0.8, "original_value": round(float(observed[position]), 6), "standardized_value": round(float(observed[position]), 6), "processing_status": "unchanged"})
            stage_rows.append({**common, "station_id": "OUTLET_DEMO", "stage_m": round(float(stage[position]), 6), "unit": "m", "measurement_method": "synthetic", "datum": "DEMO_DATUM", "uncertainty": 0.05, "original_value": round(float(stage[position]), 6), "standardized_value": round(float(stage[position]), 6), "processing_status": "unchanged"})
            if position % 3 == 0:
                assimilation_rows.append({**common, "station_id": "OUTLET_DEMO", "variable": "outlet_flow", "value": round(float(observed[position]), 6), "unit": "m3/s", "uncertainty": 0.8, "processing_status": "unchanged"})
    pd.DataFrame(event_rows).to_csv(OUTPUT / "events.csv", index=False)
    pd.DataFrame(rain_rows).to_csv(OUTPUT / "rainfall.csv", index=False)
    pd.DataFrame(flow_rows).to_csv(OUTPUT / "streamflow.csv", index=False)
    pd.DataFrame(stage_rows).to_csv(OUTPUT / "stage.csv", index=False)
    pd.DataFrame(assimilation_rows).to_csv(OUTPUT / "assimilation_observations.csv", index=False)
    pd.DataFrame([
        {"station_id": "RG_DEMO", "variable": "rainfall", "element_id": "S1", "longitude": 114.0, "latitude": 22.6, "timezone": "Asia/Shanghai", "source": "synthetic_demo", "synthetic_demo": True},
        {"station_id": "OUTLET_DEMO", "variable": "flow", "element_id": "R1", "longitude": 114.01, "latitude": 22.59, "timezone": "Asia/Shanghai", "source": "synthetic_demo", "synthetic_demo": True},
    ]).to_csv(OUTPUT / "station_metadata.csv", index=False)
    (OUTPUT / "hindcast_config.yaml").write_text(yaml.safe_dump({
        "synthetic_demo": True, "event_detection": {"method": "user_defined", "inter_event_time_hr": 12},
        "split": {"strategy": "chronological", "calibration": ["E001", "E002", "E003"], "validation": ["E004", "E005"], "test": ["E006"]},
        "calibration": {"max_candidates": 30, "event_weighting": "equal"},
    }, sort_keys=False), encoding="utf-8")
    (OUTPUT / "assimilation_config.yaml").write_text(yaml.safe_dump({
        "synthetic_demo": True, "gain": .45, "correction_decay": .8, "ensemble_size": 20,
        "observation_error": .8, "model_error": .15, "random_seed": 42,
    }, sort_keys=False), encoding="utf-8")
    (OUTPUT / "expected_metrics.json").write_text(json.dumps({
        "synthetic_demo": True, "event_count": 6, "calibration_events": 3, "validation_events": 2,
        "test_events": 1, "real_validation_level": "framework_ready_real_data_missing",
        "operational_candidate": False,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
