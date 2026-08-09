"""Validation gates for metadata-only research intake and method cards."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from hydrolite.capability_registry import get_capability
from hydrolite.research_intake import list_methods, list_sources
from hydrolite.research_method_card import METHOD_CARD_STATUSES, VALUE_ADDED_GATES, ResearchMethodCard
from hydrolite.research_source import SOURCE_TYPES, VERIFICATION_STATUSES, ResearchSource
from hydrolite.source_licensing import assess_source_license


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def _valid_url(value: str | None) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_source(source: ResearchSource) -> list[str]:
    errors: list[str] = []
    if not source.source_id or not source.title:
        errors.append("source_id_and_title_required")
    if source.source_type not in SOURCE_TYPES:
        errors.append("invalid_source_type")
    if source.verification_status not in VERIFICATION_STATUSES:
        errors.append("invalid_verification_status")
    if not _valid_url(source.primary_url):
        errors.append("invalid_primary_url")
    if source.doi and not DOI_RE.match(source.doi):
        errors.append("invalid_doi")
    if source.implementation_mode != "method_inspired_clean_room":
        errors.append("clean_room_mode_required")
    if source.copy_allowed or source.runtime_dependency_allowed:
        errors.append("copy_or_runtime_dependency_not_allowed")
    if source.full_text_local_reference:
        errors.append("local_full_text_reference_not_allowed")
    if source.verification_status == "source_incomplete" and source.source_type == "journal_article" and not source.notes:
        errors.append("incomplete_source_requires_note")
    assessment = assess_source_license(source)
    if not assessment.clean_room_required or assessment.code_reuse_allowed or assessment.text_reuse_allowed or assessment.figure_reuse_allowed:
        errors.append("license_assessment_must_preserve_clean_room")
    return errors


def validate_method_card(card: ResearchMethodCard, source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not card.method_id or not card.source_ids:
        errors.append("method_id_and_source_links_required")
    if any(source_id not in source_ids for source_id in card.source_ids):
        errors.append("unknown_source_link")
    if card.current_status not in METHOD_CARD_STATUSES:
        errors.append("method_card_status_not_admitted")
    if card.current_status == "experimental" and not card.implementation_status:
        errors.append("experimental_method_requires_implementation_status")
    if card.value_added_gate not in VALUE_ADDED_GATES or card.value_added_gate != "not_tested":
        errors.append("value_added_not_tested_required")
    if card.recommended_integration_mode != "method_inspired_clean_room":
        errors.append("clean_room_mode_required")
    if not card.not_to_copy:
        errors.append("excluded_elements_required")
    if card.method_id == "physics_graph_temporal_residual" and "true_future_forecast_blocked" not in card.causal_constraints:
        errors.append("bidirectional_future_forecast_must_be_blocked")
    if card.current_status == "experimental" and not card.validation_required:
        errors.append("experimental_method_requires_validation")
    if card.domain == "water_quality" and get_capability("water_quality")["status"] != "planned":
        errors.append("water_quality_capability_must_remain_planned")
    return errors


def validate_research_registry(
    sources: list[ResearchSource] | None = None, methods: list[ResearchMethodCard] | None = None
) -> dict[str, object]:
    source_rows = list_sources() if sources is None else sources
    method_rows = list_methods() if methods is None else methods
    source_errors = {item.source_id: validate_source(item) for item in source_rows}
    source_errors = {key: value for key, value in source_errors.items() if value}
    ids = {item.source_id for item in source_rows}
    method_errors = {item.method_id: validate_method_card(item, ids) for item in method_rows}
    method_errors = {key: value for key, value in method_errors.items() if value}
    return {
        "status": "failed" if source_errors or method_errors else "passed",
        "source_count": len(source_rows),
        "method_count": len(method_rows),
        "source_errors": source_errors,
        "method_errors": method_errors,
    }
