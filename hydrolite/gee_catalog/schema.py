from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GeeBandRecord:
    name: str
    description: str | None = None
    unit: str | None = None
    scale: float | None = None
    offset: float | None = None
    nominal_scale_m: float | None = None
    data_type: str | None = None
    wavelength: str | None = None
    valid_range: list[float] | None = None
    missing_metadata_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GeeDatasetRecord:
    asset_id: str
    catalog_id: str | None = None
    title: str | None = None
    description: str | None = None
    dataset_type: str | None = None
    provider: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    bbox: list[float] | None = None
    temporal_resolution: str | None = None
    nominal_scale_m: float | None = None
    projection: str | None = None
    bands: list[dict[str, Any]] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    license_text: str | None = None
    license_url: str | None = None
    citation: str | None = None
    doi: str | None = None
    official_catalog_url: str | None = None
    stac_url: str | None = None
    status: str | None = None
    deprecated: bool = False
    replacement_asset_ids: list[str] = field(default_factory=list)
    hydrolite_use_cases: list[str] = field(default_factory=list)
    source_metadata_hash: str | None = None
    metadata_quality: str = "unknown"
    refresh_time: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["official_url"] = row["official_catalog_url"]  # legacy reader compatibility
        row["metadata_hash"] = row["source_metadata_hash"]
        row["last_refresh"] = row["refresh_time"]
        return row


@dataclass(frozen=True)
class GeeCatalogSource:
    canonical_uri: str
    public_https_uri: str
    allowed_hosts: list[str]


@dataclass(frozen=True)
class GeeCatalogManifest:
    source_url: str
    source_type: str
    retrieval_time: str
    http_status: int | None
    etag: str | None
    last_modified: str | None
    content_hash: str | None
    parser_version: str
    hydrolite_version: str
    git_commit: str | None
    record_count: int
    failure_count: int
    validation_status: str


@dataclass(frozen=True)
class GeeSearchRequest:
    query: str | None = None
    asset_id: str | None = None
    dataset_type: str | None = None
    provider: str | None = None
    category: str | None = None
    band: str | None = None
    maximum_nominal_resolution_m: float | None = None
    maximum_matched_band_resolution_m: float | None = None
    date_start: str | None = None
    date_end: str | None = None
    full_temporal_coverage: bool = False
    bbox: list[float] | None = None
    status: str | None = None
    include_deprecated: bool = False
    license_rule: str | None = None
    use_case: str | None = None
    result_limit: int = 20
    language: str | None = None


@dataclass(frozen=True)
class GeeRelaxedAlternative:
    asset_id: str
    relaxed_conditions: list[str]
    risks: list[str]
    reason_not_exact: str


@dataclass(frozen=True)
class GeeSearchResult:
    status: str
    records: list[dict[str, Any]]
    relaxed_alternatives: list[GeeRelaxedAlternative] = field(default_factory=list)


@dataclass(frozen=True)
class GeeComparisonResult:
    status: str
    records: list[dict[str, Any]]
    differences: dict[str, Any]


@dataclass(frozen=True)
class GeeRecommendationResult:
    status: str
    model_id: str
    recommendations: list[dict[str, Any]]


@dataclass(frozen=True)
class GeeRefreshResult:
    status: str
    record_count: int = 0
    failure_count: int = 0
    message: str | None = None


@dataclass(frozen=True)
class GeeValidationResult:
    status: str
    record_count: int
    errors: dict[str, Any] = field(default_factory=dict)
    warnings: dict[str, Any] = field(default_factory=dict)


REQUIRED_FIELDS = {"asset_id", "title", "dataset_type", "provider", "status", "official_catalog_url", "stac_url", "source_metadata_hash", "refresh_time"}


def validate_record(record: dict[str, Any]) -> list[str]:
    aliases = {"official_catalog_url": "official_url", "source_metadata_hash": "metadata_hash", "refresh_time": "last_refresh"}
    return sorted(field for field in REQUIRED_FIELDS if record.get(field) is None and record.get(aliases.get(field, "")) is None)
