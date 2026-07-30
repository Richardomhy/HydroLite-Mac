import numpy as np
import pandas as pd

from hydrolite.continuous_calibration import evaluate_continuous_model, split_continuous_periods_chronologically


def test_continuous_calibration_uses_chronological_split():
    frame=pd.DataFrame({"date":pd.date_range("2000-01-01",periods=100),"value":range(100)})
    parts=split_continuous_periods_chronologically(frame,{})
    assert parts["calibration"]["date"].max()<parts["validation"]["date"].min()<parts["test"]["date"].min()
    metrics=evaluate_continuous_model(np.arange(20),np.arange(20))
    assert metrics["NSE"]==1 and metrics["KGE"]==1 and metrics["PBIAS"]==0
