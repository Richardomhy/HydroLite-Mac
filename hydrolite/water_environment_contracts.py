"""M9A source-accounting contracts; river delivery and water quality are out of scope."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class PollutionSourceType(StrEnum):
    INDUSTRIAL = "industrial"
    MUNICIPAL_DOMESTIC = "municipal_domestic"
    RURAL_DOMESTIC = "rural_domestic"
    WASTEWATER_TREATMENT = "wastewater_treatment"
    DIRECT_OUTFALL = "direct_outfall"
    CROP_AGRICULTURE = "crop_agriculture"
    ORCHARD = "orchard"
    FERTILIZER_APPLICATION = "fertilizer_application"
    PESTICIDE_RELATED_CONTEXT = "pesticide_related_context"
    PIG = "pig"
    CATTLE = "cattle"
    POULTRY = "poultry"
    OTHER_LIVESTOCK = "other_livestock"
    POND_AQUACULTURE = "pond_aquaculture"
    LAKE_AQUACULTURE = "lake_aquaculture"
    INTENSIVE_AQUACULTURE = "intensive_aquaculture"
    URBAN_RUNOFF = "urban_runoff"
    RURAL_RUNOFF = "rural_runoff"
    SOLID_WASTE_RELATED = "solid_waste_related"
    UNKNOWN = "unknown"
    USER_DEFINED = "user_defined"


POLLUTANTS = ("CODMn", "NH3-N", "TN", "TP")
EVIDENCE_TIERS = tuple(f"evidence_tier_{index}" for index in range(1, 7))


@dataclass(frozen=True, slots=True)
class Record:
    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PollutantSpec(Record):
    pollutant_id: str
    display_name: str
    canonical_load_unit: str = "kg/day"


@dataclass(frozen=True, slots=True)
class PollutionSource(Record):
    source_id: str
    source_type: str
    source_subtype: str
    name: str
    project_id: str
    geometry_type: str
    geometry_reference: str
    longitude: float | None
    latitude: float | None
    area: float | None
    administrative_unit: str
    subbasin_id: str | None
    reach_id: str | None
    activity_dataset_id: str | None
    status: str
    source_confidence: str
    provenance: dict[str, Any]
    spatial_status: str = "unmapped"


@dataclass(frozen=True, slots=True)
class ActivityRecord(Record):
    activity_id: str
    source_id: str
    activity_type: str
    value: float | None
    unit: str
    start_date: str
    end_date: str
    temporal_basis: str
    source_dataset_id: str
    field_name: str
    observed_or_estimated: str
    quality: str
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EmissionFactor(Record):
    factor_id: str
    source_type: str
    pollutant: str
    value: float | None
    numerator_unit: str
    denominator_unit: str
    temporal_basis: str
    region_applicability: str
    source_reference: str
    source_type_reference: str
    confidence: str
    uncertainty_low: float | None
    uncertainty_high: float | None
    valid_from: str
    valid_to: str
    notes: str
    approved_for_real_project: bool = False
    example: bool = False


@dataclass(frozen=True, slots=True)
class TreatmentFactor(Record):
    treatment_id: str
    source_id: str
    pollutant: str
    removal_fraction: float
    treatment_type: str
    capacity: float | None
    actual_operation_factor: float | None
    evidence: str
    confidence: str


@dataclass(frozen=True, slots=True)
class PollutionLoadRecord(Record):
    ledger_id: str
    source_id: str
    source_type: str
    pollutant: str
    generated_load: float | None
    removed_load: float | None
    net_emission_load: float | None
    unit: str
    temporal_basis: str
    evidence_tier: str
    source_activity_id: str | None
    emission_factor_id: str | None
    treatment_id: str | None
    uncertainty_low: float | None
    uncertainty_high: float | None
    uncertainty_status: str
    spatial_status: str
    calculation_status: str
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SourceLoadLedger(Record):
    records: tuple[PollutionLoadRecord, ...]
    canonical_unit: str = "kg/day"


@dataclass(frozen=True, slots=True)
class SourceInventoryValidationResult(Record):
    status: str
    source_count: int
    accepted_count: int
    unresolved_count: int
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
