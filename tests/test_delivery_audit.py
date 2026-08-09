from tests.delivery_helpers import seed_governed_delivery


def test_delivery_review_and_package_actions_write_audit_history(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.delivery_review import approve_delivery, review_delivery, submit_delivery, write_delivery_governance_outputs
    from hydrolite.deliverable_package import create_delivery_bundle
    from hydrolite.runtime_db import list_audit_event_records, list_review_records
    delivery_id = seeded["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review"); approve_delivery(delivery_id, comment="approve")
    create_delivery_bundle(delivery_id, tmp_path / "delivery.zip")
    actions = {row["action"] for row in list_audit_event_records(deliverable_id=delivery_id)}
    assert {"deliverable_created", "submitted", "reviewed", "approved", "package_exported"} <= actions
    reviews = list_review_records(deliverable_id=delivery_id)
    assert [row["action"] for row in reversed(reviews)] == ["submit", "review", "approve"]
    assert all(row["software_user_reference"] == "local_logic_role_only" for row in reviews)
    outputs = write_delivery_governance_outputs(delivery_id, tmp_path / "governance")
    assert outputs["review_history"].exists() and outputs["audit_log"].exists()
    assert outputs["delivery_readiness.json"].exists() and outputs["integrity_verification.json"].exists()
