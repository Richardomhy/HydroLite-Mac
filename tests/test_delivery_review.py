import pytest

from tests.delivery_helpers import seed_governed_delivery


def test_delivery_review_transitions_and_scientific_status_separation(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.delivery_review import approve_delivery, review_delivery, submit_delivery
    delivery_id = seeded["deliverable"]["deliverable_id"]
    assert submit_delivery(delivery_id, comment="submit")["review_status"] == "submitted_for_review"
    assert review_delivery(delivery_id, comment="review")["review_status"] == "reviewed"
    approved = approve_delivery(delivery_id, comment="approve")
    assert approved["review_status"] == "approved_for_delivery"
    assert approved["scientific_validation_level"] == "framework_ready"


def test_changes_reject_supersede_and_invalid_transition(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.delivery_review import approve_delivery, reject_delivery, request_delivery_changes, review_delivery, submit_delivery, supersede_delivery
    delivery_id = seeded["deliverable"]["deliverable_id"]
    with pytest.raises(ValueError, match="Invalid delivery transition"):
        approve_delivery(delivery_id, comment="too early")
    submit_delivery(delivery_id, comment="submit")
    assert request_delivery_changes(delivery_id, comment="fix")["review_status"] == "changes_requested"
    submit_delivery(delivery_id, comment="resubmit"); review_delivery(delivery_id, comment="review")
    approve_delivery(delivery_id, comment="approve")
    assert supersede_delivery(delivery_id, comment="new version available")["review_status"] == "superseded"

    other = seed_governed_delivery(monkeypatch, tmp_path / "other")
    other_id = other["deliverable"]["deliverable_id"]
    submit_delivery(other_id, comment="submit")
    assert reject_delivery(other_id, comment="reject")["review_status"] == "rejected"
