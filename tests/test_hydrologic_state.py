from hydrolite.event_dataset import build_event_dataset
from hydrolite.flood_events import build_event_catalog
from hydrolite.hydrologic_state import build_initial_state, validate_initial_state


def test_initial_state_is_physical():
    event = build_event_catalog("data_demo/hindcast_validation").iloc[0].to_dict()
    state = build_initial_state(event, build_event_dataset(event, "data_demo/hindcast_validation"), "projects/qgis_workflow_project")
    assert state["initial_baseflow_cms"] >= 0
    assert validate_initial_state(state)["status"] == "passed"
