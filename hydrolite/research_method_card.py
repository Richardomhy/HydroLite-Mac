"""Configuration-backed method cards, not implementations of source models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


METHOD_CARD_STATUSES = {"method_card_complete", "clean_room_ready", "experimental"}
VALUE_ADDED_GATES = {"not_tested", "demonstrated", "not_demonstrated", "insufficient_data", "unstable", "leakage_detected"}


@dataclass(frozen=True)
class ResearchMethodCard:
    method_id: str
    display_name: str
    display_name_zh: str
    source_ids: list[str]
    domain: str
    problem_type: str
    method_family: str
    method_summary: str
    core_idea: str
    borrowed_concepts: list[str]
    not_to_copy: list[str]
    required_inputs: list[str]
    optional_inputs: list[str]
    outputs: list[str]
    temporal_scale: str
    spatial_scale: str
    causal_constraints: str
    physical_constraints: str
    training_required: bool
    minimum_data_requirement: str
    validation_requirement: str
    known_strengths: list[str]
    known_weaknesses: list[str]
    leakage_risks: list[str]
    computational_cost: str
    optional_dependencies: list[str]
    HydroLite_target_components: list[str]
    recommended_integration_mode: str
    baseline_comparisons: list[str]
    value_added_gate: str
    current_status: str
    next_milestone: str
    limitations: str
    implementation_status: str | None = None
    m3_result: str | None = None
    synthetic_value_added: str | None = None
    real_data_value_added: str = "not_tested"
    output_links: list[str] | None = None
    validation_required: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchMethodCard":
        return cls(**{key: payload[key] for key in cls.__dataclass_fields__ if key in payload})

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def method_cards() -> list[dict[str, Any]]:
    from hydrolite.research_intake import list_methods

    return [card.as_dict() for card in list_methods()]
