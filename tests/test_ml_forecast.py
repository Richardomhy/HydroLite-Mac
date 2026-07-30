from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_ml_time_split_no_shuffle_and_real_data_gate(tmp_path: Path):
    from hydrolite.ml_forecast import assess_ml_data_readiness, build_ml_features, detect_feature_leakage, run_ml_synthetic_demo, split_time_series_data

    data = pd.read_csv(ROOT / "data_demo/flood_forecast/demo_ml_timeseries.csv")
    features = build_ml_features(data).dropna()
    split = split_time_series_data(features, {"method": "event_based_split"})
    assert set(split["train"]["event_id"]).isdisjoint(set(split["test"]["event_id"]))
    assert detect_feature_leakage(features, ["future_discharge_cms"])["status"] == "failed"
    assert assess_ml_data_readiness(ROOT / "projects/qgis_workflow_project")["real_training_ready"] is False
    assert run_ml_synthetic_demo(ROOT / "data_demo/flood_forecast/demo_ml_timeseries.csv", tmp_path)["status"] == "passed"
