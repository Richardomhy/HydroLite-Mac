from dataclasses import replace

from hydrolite.research_intake import get_method
from hydrolite.research_validation import validate_method_card, validate_research_registry


def test_registry_passes_and_water_quality_stays_planned():
    result = validate_research_registry()
    assert result["status"] == "passed"
    assert result["source_count"] == 5 and result["method_count"] == 4


def test_validator_blocks_future_context_and_unadmitted_status():
    card = get_method("physics_graph_temporal_residual")
    invalid = replace(card, causal_constraints="bidirectional_allowed", current_status="experimental")
    errors = validate_method_card(invalid, set(card.source_ids))
    assert "bidirectional_future_forecast_must_be_blocked" in errors
    assert "method_card_status_not_admitted" in errors
