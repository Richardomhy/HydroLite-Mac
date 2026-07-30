import pandas as pd

from hydrolite.observation_mapping import map_flow_station_to_reach, validate_observation_mapping


def test_explicit_station_mapping_is_high_confidence():
    reaches = pd.DataFrame([{"reach_id": "R1"}])
    mapping = map_flow_station_to_reach({"station_id": "Q1", "reach_id": "R1"}, reaches)
    assert mapping["confidence"] == "high"
    assert validate_observation_mapping(mapping)["status"] == "passed"
