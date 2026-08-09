"""Typed, metadata-only research-source records for the clean-room method lab."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SOURCE_TYPES = {"journal_article", "conference_paper", "github_repository", "official_documentation"}
VERIFICATION_STATUSES = {"metadata_verified", "source_incomplete", "unverified"}


@dataclass(frozen=True)
class ResearchSource:
    source_id: str
    source_type: str
    title: str
    authors: list[str]
    year: int | None
    journal: str | None
    publisher: str | None
    doi: str | None
    primary_url: str
    secondary_urls: list[str]
    repository_url: str | None
    abstract: str | None
    keywords: list[str]
    full_text_available: bool
    full_text_local_reference: str | None
    source_license: str
    license_url: str | None
    code_available: bool
    code_repository: str | None
    code_license: str
    copyright_status: str
    access_status: str
    verification_status: str
    provenance: str
    notes: str
    implementation_mode: str = "method_inspired_clean_room"
    # Kept as an alias for the M0 configuration and existing callers.
    integration_mode: str = "method_inspired_clean_room"
    copy_allowed: bool = False
    runtime_dependency_allowed: bool = False
    assets_allowed: list[str] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchSource":
        fields = cls.__dataclass_fields__
        # Omit absent optional values so dataclass defaults retain the policy.
        values = {key: payload[key] for key in fields if key in payload}
        mode = payload.get("implementation_mode", payload.get("integration_mode", "method_inspired_clean_room"))
        values["implementation_mode"] = mode
        values["integration_mode"] = mode
        return cls(**values)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
