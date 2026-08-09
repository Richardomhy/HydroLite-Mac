"""License assessments separate method inspiration from copying rights."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hydrolite.research_source import ResearchSource


@dataclass(frozen=True)
class SourceLicenseAssessment:
    source_id: str
    source_type: str
    source_license: str
    license_detected: bool
    license_url: str | None
    code_license: str
    code_reuse_allowed: bool
    text_reuse_allowed: bool
    figure_reuse_allowed: bool
    data_reuse_allowed: bool
    derivative_work_allowed: bool
    commercial_use_allowed: bool
    attribution_required: bool
    clean_room_required: bool
    usage_decision: str
    permitted_actions: list[str]
    prohibited_actions: list[str]
    review_status: str
    reviewer: str
    review_date: str | None
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_source_license(source: ResearchSource | dict[str, Any]) -> SourceLicenseAssessment:
    record = source if isinstance(source, ResearchSource) else ResearchSource.from_dict(source)
    missing = record.source_license == "license_file_missing" or record.code_license == "license_file_missing"
    copyrighted = record.source_license == "copyrighted_literature"
    decision = "clean_room_only" if missing else "method_reference_only"
    return SourceLicenseAssessment(
        source_id=record.source_id,
        source_type=record.source_type,
        source_license=record.source_license,
        license_detected=not missing,
        license_url=record.license_url,
        code_license=record.code_license,
        code_reuse_allowed=False,
        text_reuse_allowed=False,
        figure_reuse_allowed=False,
        data_reuse_allowed=False,
        derivative_work_allowed=False,
        commercial_use_allowed=not missing and not copyrighted,
        attribution_required=True,
        clean_room_required=True,
        usage_decision=decision,
        permitted_actions=["bibliographic_reference", "independent_concept_inspiration"],
        prohibited_actions=["copy_code", "copy_text", "copy_figures", "reuse_catalog_assets", "runtime_dependency"],
        review_status="approved_with_clean_room_constraints",
        reviewer="HydroLite registry policy",
        review_date=None,
        notes="Full-text access never grants redistribution or implementation-copy rights.",
    )


def audit_source_licenses() -> list[dict[str, Any]]:
    from hydrolite.research_intake import list_sources

    return [assessment.as_dict() for assessment in (assess_source_license(item) for item in list_sources())]
