import pandas as pd
from hydrolite.trend_aware_features import build_causal_temporal_context, detect_future_leakage


def test_trend_context_and_future_leakage_gate():
    dates=pd.date_range("2020-01-01",periods=5); frame=build_causal_temporal_context(range(5),dates,issue_time=dates[3])
    assert len(frame)==4 and detect_future_leakage(frame,dates[3])["status"]=="passed"
