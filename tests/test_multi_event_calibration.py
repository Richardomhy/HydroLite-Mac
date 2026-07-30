from hydrolite.calibration import create_multi_event_calibration_objective, run_multi_event_parameter_search
from hydrolite.flood_events import build_event_catalog


def test_multi_event_search_is_bounded(tmp_path):
    events = build_event_catalog("data_demo/hindcast_validation").head(2)
    assert create_multi_event_calibration_objective(events)["weighting"] == "equal"
    result = run_multi_event_parameter_search("projects/qgis_workflow_project", events, {"max_candidates": 3, "output_dir": tmp_path})
    assert len(result["candidates"]) == 3
