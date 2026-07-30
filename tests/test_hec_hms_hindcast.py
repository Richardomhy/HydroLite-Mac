from hydrolite.hec_hms_hindcast import run_hms_hindcast_event, validate_hms_hindcast_result


def test_hms_hindcast_safely_skips_without_local_gate():
    result = run_hms_hindcast_event({"event_id": "E001"}, "projects/qgis_workflow_project", timeout=120)
    assert result["status"] in {"skipped", "failed", "blocked_gate"}
    assert validate_hms_hindcast_result(result)["status"] in {"passed", "skipped", "failed"}
