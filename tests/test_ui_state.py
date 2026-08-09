from hydrolite.ui.state import AppState, ProjectState, RunState, ScenarioState, load_app_state, update_app_state


def test_ui_state_is_namespaced_and_round_trips():
    store = {}; state = update_app_state(store, current_project="P1", current_scenario="SC08", selected_run="R1", ui_mode="advanced", language="English", last_action="test")
    assert load_app_state(store) == state
    assert list(store) == ["hydrolite_app_state"]
    assert ProjectState().project_loaded is False and ScenarioState().wizard_step == 1 and RunState().run_status == "not_started"
    assert AppState().ui_mode == "simple"
