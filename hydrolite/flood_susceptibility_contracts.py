"""Contracts and quality gates for static flood-susceptibility experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd


INVENTORY_TYPES = {"verified_non_flood", "pseudo_absence", "background_sample", "unknown", "observed_flood"}
IMPLEMENTATION_NOTICE = (
    "本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，"
    "不构成原论文模型的精确复现。"
)
SUSCEPTIBILITY_RISK_NOTICE = (
    "Flood susceptibility is not flood risk; risk additionally requires hazard intensity, "
    "exposure, vulnerability, and consequence."
)


@dataclass(slots=True)
class FloodInventoryPoint:
    point_id: str
    event_id: str | None
    timestamp: Any
    label: int
    longitude: float
    latitude: float
    inventory_type: str
    verification_status: str
    source: str
    source_confidence: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FloodConditioningFactorSpec:
    factor_id: str
    unit: str
    source: str
    resolution: str
    temporal_reference: str
    categorical: bool
    derivation_method: str
    quality: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_flood_inventory(data: Any) -> pd.DataFrame:
    frame = pd.DataFrame(data).copy()
    aliases = {"flood": "label", "x": "longitude", "y": "latitude", "event_date": "timestamp"}
    frame = frame.rename(columns={key: value for key, value in aliases.items() if key in frame})
    required = {"point_id", "label", "longitude", "latitude"}
    missing = sorted(required - set(frame))
    if missing:
        raise ValueError(f"Flood inventory missing columns: {', '.join(missing)}")
    for column, default in {
        "event_id": None, "timestamp": None, "inventory_type": "unknown",
        "verification_status": "unverified", "source": "user", "source_confidence": "unknown",
        "provenance": "unspecified",
    }.items():
        if column not in frame: frame[column] = default
    frame["timestamp"] = pd.to_datetime(frame.timestamp, errors="coerce")
    frame["label"] = pd.to_numeric(frame.label, errors="coerce")
    frame["longitude"] = pd.to_numeric(frame.longitude, errors="coerce")
    frame["latitude"] = pd.to_numeric(frame.latitude, errors="coerce")
    return frame


def detect_duplicate_points(data: Any, coordinate_tolerance: int = 8) -> pd.DataFrame:
    frame = normalize_flood_inventory(data)
    coordinate_keys = [frame.longitude.round(coordinate_tolerance), frame.latitude.round(coordinate_tolerance)]
    duplicate = frame.point_id.duplicated(keep=False) | pd.MultiIndex.from_arrays(coordinate_keys).duplicated(keep=False)
    return frame[duplicate]


def detect_conflicting_labels(data: Any, coordinate_tolerance: int = 8) -> pd.DataFrame:
    frame = normalize_flood_inventory(data); frame["coord_key"] = frame.longitude.round(coordinate_tolerance).astype(str) + ":" + frame.latitude.round(coordinate_tolerance).astype(str)
    conflict_keys = frame.groupby("coord_key").label.nunique().loc[lambda value: value > 1].index
    return frame[frame.coord_key.isin(conflict_keys)].drop(columns="coord_key")


def detect_event_duplicates(data: Any) -> pd.DataFrame:
    frame = normalize_flood_inventory(data)
    return frame[frame.event_id.notna() & frame.duplicated(["event_id", "point_id"], keep=False)]


def detect_invalid_coordinates(data: Any) -> pd.DataFrame:
    frame = normalize_flood_inventory(data)
    invalid = frame.longitude.isna() | frame.latitude.isna() | ~frame.longitude.between(-180, 180) | ~frame.latitude.between(-90, 90)
    return frame[invalid]


def calculate_class_balance(data: Any) -> dict[str, Any]:
    frame = normalize_flood_inventory(data); valid = frame[frame.label.isin([0, 1])]
    flood = int((valid.label == 1).sum()); background = int((valid.label == 0).sum()); total = len(valid); prevalence = flood / total if total else np.nan
    return {"point_count": total, "flood_count": flood, "background_count": background, "prevalence": prevalence, "imbalance_detected": bool(np.isfinite(prevalence) and min(prevalence, 1 - prevalence) < 0.4), "pseudo_absence_count": int((valid.inventory_type == "pseudo_absence").sum()), "pseudo_absence_is_verified_non_flood": False}


def calculate_inventory_density(data: Any) -> dict[str, float]:
    frame = normalize_flood_inventory(data); width = float(frame.longitude.max() - frame.longitude.min()); height = float(frame.latitude.max() - frame.latitude.min()); area = width * height
    return {"coordinate_extent_area": area, "points_per_coordinate_area": len(frame) / area if area > 0 else np.nan}


def validate_flood_inventory(data: Any) -> dict[str, Any]:
    try: frame = normalize_flood_inventory(data)
    except ValueError as exc: return {"status": "failed", "errors": [str(exc)]}
    duplicates = detect_duplicate_points(frame); conflicts = detect_conflicting_labels(frame); invalid_coordinates = detect_invalid_coordinates(frame); invalid_labels = frame[~frame.label.isin([0, 1])]
    errors = []
    if len(conflicts): errors.append("conflicting_labels")
    if len(invalid_coordinates): errors.append("invalid_coordinates")
    if len(invalid_labels): errors.append("invalid_labels")
    return {"status": "passed" if not errors else "failed", "errors": errors, "duplicate_count": len(duplicates), "conflicting_label_count": len(conflicts), "invalid_coordinate_count": len(invalid_coordinates), "invalid_label_count": len(invalid_labels), "class_balance": calculate_class_balance(frame), "inventory_density": calculate_inventory_density(frame)}


def classify_inventory_quality(data: Any) -> dict[str, Any]:
    validation = validate_flood_inventory(data); balance = validation.get("class_balance", {})
    if validation["status"] == "failed": quality = "invalid"
    elif balance.get("pseudo_absence_count", 0): quality = "usable_with_pseudo_absence_warning"
    else: quality = "verified_structure_ready"
    return {"status": quality, "validation": validation, "real_validation_claim_allowed": False}


def default_factor_specs() -> dict[str, FloodConditioningFactorSpec]:
    categorical = {"land_cover", "soil", "geology"}
    units = {"elevation": "m", "slope": "degree", "aspect": "degree", "distance_to_stream": "m", "distance_to_road": "m", "distance_to_settlement": "m", "rainfall_extreme": "mm", "antecedent_rainfall": "mm", "soil_moisture": "fraction", "surface_runoff": "mm", "NDVI": "1", "imperviousness": "fraction"}
    factors = (
        "elevation", "slope", "aspect", "plan_curvature", "profile_curvature", "TWI",
        "flow_accumulation", "distance_to_stream", "distance_to_road", "distance_to_settlement",
        "land_cover", "NDVI", "soil", "imperviousness", "rainfall_extreme",
        "antecedent_rainfall", "soil_moisture", "surface_runoff",
    )
    return {factor: FloodConditioningFactorSpec(factor, units.get(factor, "1"), "synthetic_demo_or_user", "project_scale", "event_or_static", factor in categorical, "registered_factor_pipeline", "diagnostic", {"clean_room": True}) for factor in factors}


def validate_factor_spec(spec: FloodConditioningFactorSpec) -> dict[str, Any]:
    missing = [name for name in ("factor_id", "unit", "source", "resolution", "temporal_reference", "derivation_method", "quality") if not getattr(spec, name)]
    return {"status": "passed" if not missing else "failed", "missing": missing}
