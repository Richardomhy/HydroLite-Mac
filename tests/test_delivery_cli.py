from tests.delivery_helpers import seed_governed_delivery


def test_project_version_and_delivery_cli_dispatch(monkeypatch, tmp_path, capsys):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.__main__ import main
    assert main(["project", "versions", str(seeded["workspace"])]) == 0
    assert seeded["version"]["project_version_id"] in capsys.readouterr().out
    assert main(["project", "version-show", seeded["version"]["project_version_id"]]) == 0
    assert main(["delivery", "status", seeded["deliverable"]["deliverable_id"]]) == 0
    assert "delivery_review_status" in capsys.readouterr().out


def test_package_verify_cli(monkeypatch, tmp_path, capsys):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.deliverable_package import create_project_package
    from hydrolite.__main__ import main
    package = create_project_package(seeded["workspace"], tmp_path / "project.zip")
    assert main(["project", "verify-package", str(package)]) == 0
    assert '"status": "passed"' in capsys.readouterr().out
