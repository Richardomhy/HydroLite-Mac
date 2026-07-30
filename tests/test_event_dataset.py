from hydrolite.event_dataset import build_event_dataset, validate_event_dataset, write_event_dataset
from hydrolite.flood_events import build_event_catalog


def test_build_standardized_event_dataset(tmp_path):
    event = build_event_catalog("data_demo/hindcast_validation").iloc[0].to_dict()
    result = build_event_dataset(event, "data_demo/hindcast_validation")
    assert validate_event_dataset(result)["status"] == "passed"
    assert write_event_dataset(tmp_path, result)["manifest"].exists()
