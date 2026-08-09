"""User-facing scenario contracts, separate from executable workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PRODUCTION_STATUSES = {
    "production_ready", "ready_with_warnings", "experimental", "planned", "unavailable",
}
VALIDATION_LEVELS = {
    "synthetic_demo", "framework_ready", "ready_with_warnings",
    "real_data_tested", "independently_validated", "production_ready",
}


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    scenario_id: str
    name_zh: str
    name_en: str
    description: str
    business_question: str
    required_data: tuple[str, ...]
    optional_data: tuple[str, ...]
    automatic_data_sources: tuple[str, ...]
    capabilities: tuple[str, ...]
    workflow_id: str
    readiness_rules: dict[str, Any]
    output_types: tuple[str, ...]
    validation_level: str
    production_status: str
    limitations: tuple[str, ...]
    recommended_for: tuple[str, ...]
    not_recommended_for: tuple[str, ...]
    advanced: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScenarioReadiness:
    scenario_id: str
    status: str
    required: tuple[dict[str, str], ...] = field(default_factory=tuple)
    optional: tuple[dict[str, str], ...] = field(default_factory=tuple)
    warning_codes: tuple[str, ...] = field(default_factory=tuple)
    next_recommended_action: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_scenario_definition(scenario: ScenarioDefinition) -> dict[str, Any]:
    errors: list[str] = []
    if not scenario.scenario_id.startswith("SC"):
        errors.append("invalid_scenario_id")
    if scenario.production_status not in PRODUCTION_STATUSES:
        errors.append("invalid_production_status")
    if scenario.validation_level not in VALIDATION_LEVELS:
        errors.append("invalid_validation_level")
    if not scenario.workflow_id:
        errors.append("workflow_mapping_missing")
    if scenario.production_status == "production_ready" and scenario.validation_level != "production_ready":
        errors.append("production_status_exceeds_validation")
    return {"status": "passed" if not errors else "failed", "errors": errors}
