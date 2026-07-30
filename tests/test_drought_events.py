import pandas as pd

from hydrolite.drought_events import build_drought_event_catalog, detect_drought_events


def test_drought_event_duration_and_single_value_rejection():
    series=pd.Series([0,-1.2,-1.4,0,-1.1,0],index=pd.date_range("2020-01-01",periods=6,freq="MS"))
    assert len(detect_drought_events(series,-1,2))==1
    catalog=build_drought_event_catalog(pd.DataFrame({"SPI":series}))
    assert len(catalog)==1 and catalog.iloc[0]["duration"]==2
