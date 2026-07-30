from tests.runtime_helpers import configure_runtime, make_workspace


def test_project_registration_readiness_archive_snapshot(monkeypatch, tmp_path):
    configure_runtime(monkeypatch, tmp_path); workspace = make_workspace(tmp_path)
    from hydrolite.project_service import archive_project, create_project_snapshot, register_workspace_as_project, update_project_readiness
    first = register_workspace_as_project(workspace); second = register_workspace_as_project(workspace)
    assert first["project_id"] == second["project_id"]
    assert update_project_readiness(first["project_id"])["status"] == "ready"
    assert create_project_snapshot(first["project_id"], tmp_path / "snapshots").exists()
    assert archive_project(first["project_id"])["status"] == "archived"
    assert workspace.exists()
