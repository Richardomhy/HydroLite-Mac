from hydrolite.event_split import detect_event_leakage, split_events_chronologically, split_events_leave_one_event_out, validate_event_split
from hydrolite.flood_events import build_event_catalog


def test_chronological_split_has_independent_test():
    catalog = build_event_catalog("data_demo/hindcast_validation")
    split = split_events_chronologically(catalog)
    assert [len(split[key]) for key in ("calibration", "validation", "test")] == [3, 2, 1]
    assert not detect_event_leakage(split)
    assert validate_event_split(split)["status"] == "passed"
    assert len(split_events_leave_one_event_out(catalog)) == 6
