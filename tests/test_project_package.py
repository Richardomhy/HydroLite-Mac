from pathlib import Path
import zipfile

from tests.delivery_helpers import seed_governed_delivery


def _approve(seed):
    from hydrolite.delivery_review import approve_delivery, review_delivery, submit_delivery
    delivery_id = seed["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review"); approve_delivery(delivery_id, comment="approve")
    return delivery_id


def test_delivery_thin_and_portable_packages_verify(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    delivery_id = _approve(seeded)
    from hydrolite.deliverable_package import create_delivery_bundle, create_project_package
    from hydrolite.integrity_verification import verify_project_package
    delivery_bundle = create_delivery_bundle(delivery_id, tmp_path / "delivery.zip")
    thin = create_project_package(seeded["workspace"], tmp_path / "thin.zip", mode="thin")
    selected = tmp_path / "selected.csv"; selected.write_text("id,value\n1,2\n", encoding="utf-8")
    portable = create_project_package(seeded["workspace"], tmp_path / "portable.zip", mode="portable", selected_data=[selected])
    assert delivery_bundle.exists()
    assert verify_project_package(thin)["status"] == "passed"
    assert verify_project_package(portable)["status"] == "passed"
    assert verify_project_package(portable)["package_schema_version"] == 1


def test_verified_import_conflict_creates_copy_and_never_overwrites(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.deliverable_package import create_project_package, import_project_package
    package = create_project_package(seeded["workspace"], tmp_path / "thin.zip")
    imported = import_project_package(package, tmp_path / "imports")
    copied = import_project_package(package, tmp_path / "imports2")
    assert imported["status"] == "imported"
    assert copied["conflict_handling"] == "copied"
    assert seeded["workspace"].exists()


def test_packages_sanitize_home_paths_without_changing_source(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    report_path = Path(seeded["report"]["path"])
    home_path = f"{Path.home()}/private/project/result.csv"
    report_path.write_text(f"# Report\n\nSource: {home_path}\n", encoding="utf-8")
    from hydrolite.integrity_verification import hash_file
    from hydrolite.runtime_db import update_artifact_record
    update_artifact_record(seeded["report"]["artifact_id"], checksum=hash_file(report_path), size_bytes=report_path.stat().st_size)
    delivery_id = _approve(seeded)
    from hydrolite.deliverable_package import create_delivery_bundle, create_project_package
    bundle = create_delivery_bundle(delivery_id, tmp_path / "delivery.zip")
    portable = create_project_package(
        seeded["workspace"],
        tmp_path / "portable.zip",
        mode="portable",
        selected_artifact_ids=[seeded["report"]["artifact_id"]],
    )
    assert home_path in report_path.read_text(encoding="utf-8")
    for package in (bundle, portable):
        with zipfile.ZipFile(package) as archive:
            packaged = b"\n".join(archive.read(name) for name in archive.namelist() if not name.endswith("/"))
        assert str(Path.home()).encode() not in packaged
        assert b"<HOME>/private/project/result.csv" in packaged
