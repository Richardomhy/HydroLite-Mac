"""Public acquisition contracts; metadata availability is not measurement readiness."""
from dataclasses import asdict, dataclass, field
from typing import Any

STRATEGIES = {"AUTO_FETCH", "AUTO_DISCOVER_REQUIRE_APPROVAL", "USER_REQUIRED"}
AUTH_TYPES = {"none", "api_key", "oauth", "service_account", "external_cli", "user_login_required"}
PROJECT_TYPES = {"outfall_actual_flow", "wastewater_volume", "outfall_concentration", "coordinate_crs", "receiving_water", "project_factor_approval", "streamflow_observed", "field_survey", "calibrated_parameters"}


@dataclass(frozen=True)
class DataRequirement:
    requirement_id: str
    data_type: str
    variables: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    spatial_extent: tuple[float, ...] = ()
    temporal_extent: tuple[str, ...] = ()
    preferred_resolution: float | None = None
    minimum_resolution: float | None = None  # maximum acceptable pixel size in metres
    required: bool = True
    quality_rules: dict = field(default_factory=dict)
    acceptable_sources: tuple[str, ...] = ()
    preferred_connectors: tuple[str, ...] = ()
    allow_auto_fetch: bool = False
    requires_project_measurement: bool = False
    fallback_strategy: str = "USER_REQUIRED"

    def __post_init__(self):
        if not self.requirement_id or not self.data_type or self.fallback_strategy not in STRATEGIES:
            raise ValueError("Invalid requirement identity or fallback strategy")
        if self.minimum_resolution is not None and self.minimum_resolution <= 0:
            raise ValueError("minimum_resolution must be positive metres")
        if self.spatial_extent and (len(self.spatial_extent) != 4 or not (-180 <= self.spatial_extent[0] < self.spatial_extent[2] <= 180 and -90 <= self.spatial_extent[1] < self.spatial_extent[3] <= 90)):
            raise ValueError("Invalid WGS84 bbox")

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DatasetCandidate:
    dataset_id: str
    connector_id: str
    provider: str
    data_type: str
    source_url: str = ""
    version: str = ""
    variables: tuple[str, ...] = ()
    spatial_extent: tuple[float, ...] = ()
    temporal_extent: tuple[str, ...] = ()
    resolution: float | None = None
    crs: str | None = None
    nodata: Any = None
    license: str = "unknown"
    license_status: str = "unknown"
    trusted_provider: bool = False
    access_status: str = "discover_only"
    estimated_size: int | None = None
    content_type: str = ""
    checksum: str = ""
    metadata: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class FetchedDataset:
    status: str
    candidate: dict = field(default_factory=dict)
    local_path: str = ""
    checksum: str = ""
    retrieved_at: str = ""
    etag: str = ""
    last_modified: str = ""
    normalized_artifact: str = ""
    processing_chain: tuple[str, ...] = ()
    error_message: str = ""

    def as_dict(self):
        return asdict(self)
