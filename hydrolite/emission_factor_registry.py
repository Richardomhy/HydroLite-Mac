"""YAML-backed emission factors. Example factors are blocked for real projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from hydrolite.water_environment_contracts import EmissionFactor, POLLUTANTS, PollutionSourceType


FACTOR_SOURCE_TYPES = {
    "official_standard", "local_official", "literature", "project_measured",
    "project_derived", "user_defined", "unknown",
}


def load_emission_factors(path: str | Path) -> list[EmissionFactor]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [EmissionFactor(**row) for row in payload.get("factors", [])]


def validate_emission_factor(factor: EmissionFactor) -> dict[str, Any]:
    errors = []
    if factor.source_type not in {item.value for item in PollutionSourceType}: errors.append("unknown_source_type")
    if factor.pollutant not in POLLUTANTS: errors.append("unsupported_pollutant")
    if factor.source_type_reference not in FACTOR_SOURCE_TYPES: errors.append("unknown_factor_source_type")
    if not factor.numerator_unit or not factor.denominator_unit: errors.append("factor_units_missing")
    if not factor.source_reference: errors.append("factor_source_reference_missing")
    if factor.value is not None and factor.value < 0: errors.append("negative_factor")
    if any(value is not None and value < 0 for value in (factor.uncertainty_low, factor.uncertainty_high)): errors.append("negative_uncertainty_bound")
    if factor.uncertainty_low is not None and factor.uncertainty_high is not None and factor.uncertainty_low > factor.uncertainty_high: errors.append("invalid_uncertainty_range")
    if factor.example and factor.approved_for_real_project: errors.append("example_factor_cannot_be_project_approved")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def register_emission_factor(factors: list[EmissionFactor], factor: EmissionFactor) -> list[EmissionFactor]:
    if validate_emission_factor(factor)["status"] != "passed": raise ValueError("Invalid emission factor")
    if any(item.factor_id == factor.factor_id for item in factors): raise ValueError(f"Duplicate factor_id: {factor.factor_id}")
    return [*factors, factor]


def compare_emission_factors(factors: list[EmissionFactor], source_type: str, pollutant: str) -> list[dict[str, Any]]:
    return [factor.as_dict() for factor in factors if factor.source_type == source_type and factor.pollutant == pollutant]


def resolve_emission_factor(
    factors: list[EmissionFactor], source_type: str, pollutant: str, *,
    real_project: bool = True, allow_example_factors: bool = False,
) -> dict[str, Any]:
    candidates = [factor for factor in factors if factor.source_type == source_type and factor.pollutant == pollutant and validate_emission_factor(factor)["status"] == "passed"]
    if not candidates: return {"status": "emission_factor_missing", "factor": None}
    approved = [factor for factor in candidates if factor.approved_for_real_project and (allow_example_factors or not factor.example)]
    if real_project and not approved:
        return {"status": "factor_not_approved_for_real_project", "factor": None, "candidates": candidates}
    return {"status": "resolved", "factor": (approved or candidates)[0], "candidates": candidates}


def audit_emission_factors(factors: list[EmissionFactor]) -> list[dict[str, Any]]:
    return [{**factor.as_dict(), **validate_emission_factor(factor)} for factor in factors]
