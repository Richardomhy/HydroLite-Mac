"""Typed contracts for the experimental multi-station water-quality lab."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


CORE_VARIABLES = ("CODMn", "NH3-N", "TN", "TP")
OPTIONAL_VARIABLES = ("DO", "water_temperature", "turbidity", "conductivity", "pH", "TSS")
QUALITY_FLAGS = {
    "valid", "suspect", "invalid", "below_detection_limit", "missing",
    "duplicate", "unit_error", "range_warning", "stale",
}
NON_DETECT_METHODS = {"preserve_qualifier", "half_detection_limit", "detection_limit", "missing"}
ALIGNMENT_METHODS = {"exact", "nearest_with_tolerance", "daily", "daily_aggregation"}
HYDROLOGIC_CONTEXTS = {"dry_weather", "wet_weather", "storm_response", "recession", "unknown"}
HORIZONS_DAYS = (1, 3, 7, 14)
EXPERIMENT_NOTICE = (
    "本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，"
    "不构成原论文模型的精确复现。"
)


@dataclass(slots=True)
class WaterQualityVariableSpec:
    variable_id: str
    display_name: str
    unit: str = "mg/L"
    canonical_unit: str = "mg/L"
    variable_type: str = "concentration"
    supports_load_conversion: bool = True
    nonnegative: bool = True
    valid_range: tuple[float | None, float | None] = (0.0, None)
    detection_limit: float | None = None
    missing_value_policy: str = "preserve_missing"
    aggregation_policy: str = "daily_mean"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WaterQualityObservation:
    station_id: str
    timestamp: Any
    variable: str
    value: float | None
    reach_id: str | None = None
    unit: str = "mg/L"
    canonical_value: float | None = None
    canonical_unit: str = "mg/L"
    detection_limit: float | None = None
    below_detection_limit: bool = False
    qualifier: str | None = None
    qc_flag: str = "valid"
    source_dataset_id: str = "user"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WaterQualityStation:
    station_id: str
    name: str = ""
    reach_id: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    mapping_method: str = "unresolved"
    mapping_confidence: str = "low"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WaterQualityDataset:
    observations: list[WaterQualityObservation]
    stations: list[WaterQualityStation]
    variable_specs: dict[str, WaterQualityVariableSpec]
    synthetic_demo: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WaterQualityForecastIssue:
    issue_time: Any
    station_id: str
    variable_id: str
    horizon_days: int
    feature_cutoff_time: Any


@dataclass(slots=True)
class WaterQualityForecastRecord:
    issue_time: Any
    valid_time: Any
    lead: int
    station_id: str
    variable: str
    prediction: float | None
    unit: str
    model_id: str
    feature_groups: list[str]
    forecast_mode: str
    data_as_of: Any
    is_synthetic: bool
    uncertainty_status: str
    observed: float | None = None
    lower: float | None = None
    upper: float | None = None


@dataclass(slots=True)
class WaterQualityLoadRecord:
    timestamp: Any
    station_id: str
    variable_id: str
    concentration_mg_l: float | None
    flow_cms: float | None
    load_kg_day: float | None
    status: str
    alignment_method: str
    source_concentration: str
    source_flow: str


@dataclass(slots=True)
class WaterQualityValidationResult:
    status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_variable_specs() -> dict[str, WaterQualityVariableSpec]:
    specs = {
        variable: WaterQualityVariableSpec(variable, variable, detection_limit=0.01)
        for variable in CORE_VARIABLES
    }
    specs.update({
        "DO": WaterQualityVariableSpec("DO", "DO", supports_load_conversion=False),
        "water_temperature": WaterQualityVariableSpec("water_temperature", "Water temperature", "degC", "degC", "state", False, False, (-10.0, 60.0)),
        "turbidity": WaterQualityVariableSpec("turbidity", "Turbidity", "NTU", "NTU", "state", False),
        "conductivity": WaterQualityVariableSpec("conductivity", "Conductivity", "uS/cm", "uS/cm", "state", False),
        "pH": WaterQualityVariableSpec("pH", "pH", "1", "1", "state", False, False, (0.0, 14.0)),
        "TSS": WaterQualityVariableSpec("TSS", "TSS", detection_limit=0.1),
    })
    return specs


def validate_variable_spec(spec: WaterQualityVariableSpec) -> WaterQualityValidationResult:
    errors: list[str] = []
    if not spec.variable_id:
        errors.append("variable_id is required")
    if not spec.canonical_unit:
        errors.append("canonical_unit is required")
    lower, upper = spec.valid_range
    if lower is not None and upper is not None and lower > upper:
        errors.append("valid_range lower bound exceeds upper bound")
    if spec.detection_limit is not None and spec.detection_limit < 0:
        errors.append("detection_limit must be nonnegative")
    return WaterQualityValidationResult("passed" if not errors else "failed", errors)
