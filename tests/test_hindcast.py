from hydrolite.hindcast import run_hydrolite_hindcast_batch


def test_multi_event_hindcast_succeeds(tmp_path):
    result = run_hydrolite_hindcast_batch("projects/qgis_workflow_project", output_dir=tmp_path)
    assert result["success_count"] == 6
    assert result["failure_count"] == 0
    assert all(abs(value) <= 5 for value in result["events"]["water_balance_error_percent"])
