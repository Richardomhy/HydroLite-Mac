from pathlib import Path

import pandas as pd

from hydrolite.drought_ml import assess_drought_ml_readiness, run_drought_ml_synthetic_demo, split_drought_ml_data_chronologically


def test_drought_ml_gate_and_synthetic_demo(tmp_path: Path):
    frame=pd.DataFrame({"date":pd.date_range("2020-01-01",periods=100),"value":range(100)})
    assert assess_drought_ml_readiness(frame)["ml_real_data_readiness"]=="insufficient_data"
    synthetic=pd.DataFrame({"date":pd.date_range("2000-01-01",periods=3650),"value":range(3650),"synthetic_demo":True})
    assert assess_drought_ml_readiness(synthetic)["status"]=="synthetic_demo_only"
    parts=split_drought_ml_data_chronologically(frame)
    assert parts["train"]["date"].max()<parts["test"]["date"].min()
    assert run_drought_ml_synthetic_demo(tmp_path)["synthetic_demo"]
