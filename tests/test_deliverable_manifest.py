from tests.delivery_helpers import seed_governed_delivery


def test_manifest_has_required_governance_sections_hash_and_sanitized_paths(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.deliverable_manifest import build_deliverable_manifest, write_deliverable_manifest
    from hydrolite.integrity_verification import hash_manifest
    paths = write_deliverable_manifest(seeded["deliverable"]["deliverable_id"])
    manifest = build_deliverable_manifest(seeded["deliverable"]["deliverable_id"])
    required = {"project", "project_version", "scenarios", "data_snapshot", "configuration_snapshot", "runs", "tasks", "models", "capabilities", "artifacts", "reports", "environment", "validation", "warnings", "limitations", "review_status", "checksums", "software_version", "git_commit", "generated_time"}
    assert required <= manifest.keys()
    assert hash_manifest(manifest) == manifest["manifest_hash"]
    assert "minghenyu" not in paths["manifest"].read_text(encoding="utf-8")
    assert "Delivery approval is separate" in paths["manifest"].read_text(encoding="utf-8")


def test_approved_report_gets_delivery_metadata_sidecar_without_changing_report(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.delivery_review import approve_delivery, review_delivery, submit_delivery
    report_path = __import__("pathlib").Path(seeded["report"]["path"])
    before = report_path.read_bytes()
    delivery_id = seeded["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review"); approve_delivery(delivery_id, comment="approve")
    sidecar = report_path.with_suffix(report_path.suffix + ".delivery.json")
    assert sidecar.exists() and report_path.read_bytes() == before
    text = sidecar.read_text(encoding="utf-8")
    assert "approved_for_delivery" in text and "framework_ready" in text
