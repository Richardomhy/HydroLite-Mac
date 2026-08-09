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
