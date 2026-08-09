import pandas as pd

from hydrolite.spatial_validation import detect_event_leakage, detect_preprocessing_leakage, detect_validation_leakage


def test_event_preprocessing_and_test_selection_leakage_are_blocked():
    frame = pd.DataFrame({"split": ["train", "test"], "event_id": ["E1", "E1"]})
    assert detect_event_leakage(frame)["status"] == "failed"
    assert detect_preprocessing_leakage({"fit_split": "all"})["status"] == "failed"
    assert detect_validation_leakage({"test_used_for_selection": True})["status"] == "failed"
