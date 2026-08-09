from tests.delivery_helpers import seed_governed_delivery


def test_frozen_artifact_and_tampered_copy_detection(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.delivery_review import approve_delivery, review_delivery, submit_delivery
    from hydrolite.integrity_verification import verify_artifact, verify_deliverable
    delivery_id = seeded["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review"); approve_delivery(delivery_id, comment="approve")
    assert verify_deliverable(delivery_id)["status"] == "passed"
    tampered = tmp_path / "tampered_copy.csv"
    tampered.write_text("changed\n", encoding="utf-8")
    assert verify_artifact(seeded["artifact"]["artifact_id"], tampered)["status"] == "failed"
    assert verify_artifact(seeded["artifact"]["artifact_id"])["status"] == "passed"


def test_approved_manifest_is_not_regenerated_on_export(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.delivery_review import approve_delivery, review_delivery, submit_delivery
    from hydrolite.deliverable_package import create_delivery_bundle
    from hydrolite.runtime_db import get_deliverable_record
    delivery_id = seeded["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review"); approve_delivery(delivery_id, comment="approve")
    before = get_deliverable_record(delivery_id)["manifest_hash"]
    create_delivery_bundle(delivery_id, tmp_path / "delivery.zip")
    assert get_deliverable_record(delivery_id)["manifest_hash"] == before


def test_in_place_artifact_overwrite_is_rejected(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.artifact_store import register_artifact
    from hydrolite.delivery_review import approve_delivery, review_delivery, submit_delivery
    delivery_id = seeded["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review"); approve_delivery(delivery_id, comment="approve")
    path = seeded["workspace"].parent / "runtime" / "runs" / seeded["run_id"] / "artifacts" / "result_v1.csv"
    path.write_text("changed\n", encoding="utf-8")
    try: register_artifact(seeded["run_id"], None, path)
    except ValueError as exc: assert "new artifact version" in str(exc)
    else: raise AssertionError("in-place overwrite accepted")


def test_new_artifact_version_records_superseded_lineage(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.artifact_store import register_artifact
    from hydrolite.runtime_paths import ensure_runtime_directories
    new_path = ensure_runtime_directories(seeded["run_id"])["artifacts"] / "result_v2.csv"
    new_path.write_text("datetime,flow\n2026-01-01T00:00:00,1.3\n")
    current = register_artifact(seeded["run_id"], None, new_path, supersedes_artifact_id=seeded["artifact"]["artifact_id"])
    assert current["artifact_version"] == 2
    assert current["supersedes_artifact_id"] == seeded["artifact"]["artifact_id"]
