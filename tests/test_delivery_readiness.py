import pytest

from tests.delivery_helpers import seed_governed_delivery


def test_missing_warning_acknowledgment_blocks_then_allows_experimental_approval(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(
        monkeypatch, tmp_path, warning="XAI_IMPORTANCE_UNSTABLE", validation="synthetic_demo",
        capabilities=("flood_susceptibility", "flood_susceptibility_xai"),
    )
    from hydrolite.delivery_review import acknowledge_warning, approve_delivery, assess_delivery_readiness, review_delivery, submit_delivery
    delivery_id = seeded["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review")
    readiness = assess_delivery_readiness(delivery_id)
    assert any("warning_acknowledgment_missing" in item for item in readiness["blockers"])
    with pytest.raises(ValueError, match="Approval blocked"):
        approve_delivery(delivery_id, comment="premature")
    for code in ("REAL_DATA_VALIDATION_MISSING", "XAI_IMPORTANCE_UNSTABLE"):
        acknowledge_warning(delivery_id, code, actor="reviewer", comment="Reviewed; not resolved.")
    approved = approve_delivery(delivery_id, comment="approved with experimental warning")
    assert approved["scientific_validation_level"] == "synthetic_demo"
    assert approved["review_status"] == "approved_for_delivery"
    from hydrolite.deliverable_manifest import build_deliverable_manifest
    manifest = build_deliverable_manifest(delivery_id)
    assert manifest["validation"] == {
        "scientific_validation_level": "synthetic_demo",
        "real_data_validation": False,
        "experimental": True,
        "xai_stability": "unstable",
        "complex_model_value_added": "not_demonstrated",
    }
    assert manifest["delivery_labels"] == ["EXPERIMENTAL"]


def test_planned_water_quality_cannot_claim_production_result(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(
        monkeypatch, tmp_path, capabilities=("water_quality",), claim="production_model_result",
    )
    from hydrolite.delivery_review import assess_delivery_readiness, review_delivery, submit_delivery
    delivery_id = seeded["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review")
    readiness = assess_delivery_readiness(delivery_id)
    assert "planned_capability_cannot_claim_production:water_quality" in readiness["blockers"]


def test_missing_validation_metadata_blocks_approval(monkeypatch, tmp_path):
    seeded = seed_governed_delivery(monkeypatch, tmp_path)
    from hydrolite.delivery_review import assess_delivery_readiness, review_delivery, submit_delivery
    from hydrolite.runtime_db import update_deliverable_record
    delivery_id = seeded["deliverable"]["deliverable_id"]
    submit_delivery(delivery_id, comment="submit"); review_delivery(delivery_id, comment="review")
    update_deliverable_record(delivery_id, scientific_validation_level="")
    assert "validation_level_missing" in assess_delivery_readiness(delivery_id)["blockers"]
