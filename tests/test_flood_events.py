import pandas as pd

from hydrolite.flood_events import build_event_catalog, detect_flood_events, validate_flood_event


def test_detect_and_validate_demo_events():
    rain = pd.read_csv("data_demo/hindcast_validation/rainfall.csv")
    events = detect_flood_events(rain, config={"minimum_inter_event_hours": 24})
    assert events
    catalog = build_event_catalog("data_demo/hindcast_validation")
    assert len(catalog) == 6
    assert validate_flood_event(catalog.iloc[0].to_dict())["status"] == "passed"
