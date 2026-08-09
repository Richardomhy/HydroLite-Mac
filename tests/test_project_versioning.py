from tests.delivery_helpers import make_delivery_workspace


def test_project_versions_have_numeric_sequence_parent_and_immutable_snapshots(monkeypatch, tmp_path):
    workspace = make_delivery_workspace(monkeypatch, tmp_path)
    from hydrolite.project_versioning import create_project_version, list_project_versions
    from hydrolite.runtime_db import get_configuration_snapshot_record

    first = create_project_version(workspace, scenario_ids=["demo"])
    original = get_configuration_snapshot_record(first["configuration_snapshot_id"])
    case = workspace / "cases" / "demo.yaml"
    case.write_text(case.read_text().replace("cn: 75", "cn: 80"), encoding="utf-8")
    second = create_project_version(workspace, scenario_ids=["demo"])
    assert first["version_number"] == 1 and second["version_number"] == 2
    assert second["parent_version_id"] == first["project_version_id"]
    assert first["configuration_snapshot_id"] != second["configuration_snapshot_id"]
    assert get_configuration_snapshot_record(first["configuration_snapshot_id"])["checksum"] == original["checksum"]
    assert [row["version_number"] for row in list_project_versions(workspace)] == [1, 2]


def test_formal_run_linkage_and_legacy_run_warning(monkeypatch, tmp_path):
    workspace = make_delivery_workspace(monkeypatch, tmp_path)
    from hydrolite.project_versioning import create_project_version, link_run_to_project_version
    from hydrolite.runtime_db import create_run_record

    version = create_project_version(workspace)
    create_run_record(run_id="legacy", project_id=version["project_id"], workflow_id="x", status="succeeded", legacy_unversioned=True)
    linked = link_run_to_project_version("legacy", version["project_version_id"])
    assert linked["legacy_unversioned"] == 0
    assert linked["data_snapshot_id"] == version["data_snapshot_id"]
    assert linked["configuration_snapshot_id"] == version["configuration_snapshot_id"]
    assert linked["environment_id"].startswith("env_")
    from hydrolite.runtime_db import get_environment_record
    environment = get_environment_record(linked["environment_id"])["payload"]
    assert {"pandas", "numpy", "scipy"} <= environment["critical_packages"].keys()
    assert "executable" not in environment
