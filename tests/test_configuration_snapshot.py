from tests.delivery_helpers import make_delivery_workspace


def test_configuration_snapshot_has_parameter_provenance_for_every_value(monkeypatch, tmp_path):
    workspace = make_delivery_workspace(monkeypatch, tmp_path)
    from hydrolite.project_versioning import PARAMETER_SOURCE_TYPES, create_configuration_snapshot
    snapshot = create_configuration_snapshot(workspace, scenario_id="demo", workflow_id="watershed_hydrology")
    assert snapshot["parameter_provenance"]
    assert all(row["source_type"] in PARAMETER_SOURCE_TYPES for row in snapshot["parameter_provenance"])
    assert all({"parameter_name", "value", "unit", "source_type", "source_reference", "confidence"} <= row.keys() for row in snapshot["parameter_provenance"])
    assert snapshot["workflow_id"] == "watershed_hydrology"
