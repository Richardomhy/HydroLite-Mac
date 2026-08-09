from hydrolite.research_intake import get_method, list_methods
from hydrolite.research_method_card import METHOD_CARD_STATUSES


def test_method_cards_are_admission_records_not_implementations():
    cards = list_methods()
    assert len(cards) == 4
    assert all(card.current_status in METHOD_CARD_STATUSES for card in cards)
    assert all(card.value_added_gate == "not_tested" for card in cards)
    assert all(card.not_to_copy for card in cards)


def test_bidirectional_method_is_blocked_for_true_future_forecast():
    card = get_method("physics_graph_temporal_residual")
    assert "true_future_forecast_blocked" in card.causal_constraints
    assert "BiLSTM" in card.limitations


def test_m4_method_cards_are_experimental_and_require_real_validation():
    graph = get_method("physics_graph_temporal_residual")
    trend = get_method("trend_graph_multihorizon_water_quality")
    assert graph.current_status == trend.current_status == "experimental"
    assert graph.validation_required is True and trend.validation_required is True
    assert "deep graph model" in graph.limitations
    assert "water-quality model is not implemented" in trend.limitations
