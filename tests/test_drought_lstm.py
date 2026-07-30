from pathlib import Path

import pandas as pd

from hydrolite.drought_lstm import assess_drought_lstm_readiness, run_drought_lstm_synthetic_smoke_test


def test_drought_lstm_is_optional_and_never_trains(tmp_path: Path):
    readiness=assess_drought_lstm_readiness()
    assert readiness["lstm_real_data_readiness"]=="insufficient_data"
    synthetic=pd.DataFrame({"synthetic_demo":[True]*5000})
    assert assess_drought_lstm_readiness(synthetic)["lstm_real_data_readiness"]=="insufficient_data"
    result=run_drought_lstm_synthetic_smoke_test(tmp_path)
    assert result["executed"] is False
    assert (tmp_path/"lstm_readiness.json").exists()
