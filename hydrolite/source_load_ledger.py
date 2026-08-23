"""Generated and net-emission accounting; no pollutant delivery or river process model."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, Iterable

import pandas as pd

from hydrolite.emission_factor_registry import resolve_emission_factor
from hydrolite.unit_system import convert_unit
from hydrolite.water_quality_load import concentration_flow_to_load
from hydrolite.water_environment_contracts import ActivityRecord, EmissionFactor, POLLUTANTS, PollutionLoadRecord, TreatmentFactor


def _factor_evidence_tier(factor: EmissionFactor | None) -> str:
    if factor is None: return "unknown"
    return {
        "project_measured": "evidence_tier_3", "project_derived": "evidence_tier_3",
        "local_official": "evidence_tier_3", "official_standard": "evidence_tier_4",
        "literature": "evidence_tier_5", "user_defined": "evidence_tier_6", "unknown": "evidence_tier_6",
    }.get(factor.source_type_reference, "unknown")


def calculate_generated_load(activity: ActivityRecord, factor: EmissionFactor) -> dict[str, float | None | str]:
    if activity.value is None: return {"status": "activity_missing", "central": None, "low": None, "high": None}
    if activity.value < 0: raise ValueError("Activity value cannot be negative")
    try:
        activity_value = float(convert_unit([activity.value], activity.unit, factor.denominator_unit).normalized_value.iloc[0])
    except ValueError as exc:
        raise ValueError(f"Activity/factor units do not match: {activity.unit} != {factor.denominator_unit}") from exc
    if factor.value is None: return {"status": "emission_factor_missing", "central": None, "low": None, "high": None}
    values = [activity_value * factor.value]
    values += [activity_value * value if value is not None else None for value in (factor.uncertainty_low, factor.uncertainty_high)]
    converted = [None if value is None else float(convert_unit([value], factor.numerator_unit, "kg/day").normalized_value.iloc[0]) for value in values]
    return {"status": "calculated", "central": converted[0], "low": converted[1], "high": converted[2]}


def calculate_measured_load(concentration_mg_l: float, flow_cms: float) -> dict[str, float | str]:
    value = float(concentration_flow_to_load([concentration_mg_l], [flow_cms])[0])
    if pd.isna(value): raise ValueError("Measured concentration and flow must be finite and non-negative")
    return {"status": "measured", "load_kg_day": value, "evidence_tier": "evidence_tier_1", "formula": "mg/L * m3/s * 86.4"}


def validate_activity_record(activity: ActivityRecord) -> dict[str, Any]:
    errors = []
    if activity.value is None: errors.append("activity_value_missing")
    elif activity.value < 0: errors.append("negative_activity")
    if not activity.unit: errors.append("activity_unit_missing")
    try:
        if activity.start_date and activity.end_date and pd.Timestamp(activity.end_date) < pd.Timestamp(activity.start_date): errors.append("invalid_activity_period")
    except Exception: errors.append("invalid_activity_date")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def validate_treatment_factor(treatment: TreatmentFactor) -> dict[str, Any]:
    errors = []
    if not 0 <= treatment.removal_fraction <= 1: errors.append("invalid_removal_fraction")
    if treatment.actual_operation_factor is not None and not 0 <= treatment.actual_operation_factor <= 1: errors.append("invalid_operation_factor")
    if treatment.capacity is not None and treatment.capacity < 0: errors.append("negative_treatment_capacity")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def apply_treatment(generated_load: float, treatment: TreatmentFactor | None) -> tuple[float, float]:
    if generated_load < 0: raise ValueError("Generated load cannot be negative")
    removal = 0.0 if treatment is None else treatment.removal_fraction
    if not 0 <= removal <= 1: raise ValueError("Treatment removal_fraction must be between 0 and 1")
    actual = 1.0 if treatment is None or treatment.actual_operation_factor is None else treatment.actual_operation_factor
    if not 0 <= actual <= 1: raise ValueError("Treatment actual_operation_factor must be between 0 and 1")
    removed = generated_load * removal * actual
    return removed, generated_load - removed


def build_source_load_ledger(
    sources: pd.DataFrame, activities: Iterable[ActivityRecord], factors: list[EmissionFactor],
    treatments: Iterable[TreatmentFactor] = (), *, real_project: bool = True,
) -> pd.DataFrame:
    activity_by_source = {item.source_id: item for item in activities}
    treatment_by_key = {(item.source_id, item.pollutant): item for item in treatments}
    rows = []
    for source in sources.loc[sources.status.isin(["accepted", "manual_confirmation_required"])].itertuples(index=False):
        for pollutant in POLLUTANTS:
            activity = activity_by_source.get(source.source_id)
            resolution = resolve_emission_factor(factors, source.source_type, pollutant, real_project=real_project)
            factor = resolution.get("factor")
            if activity is None:
                result = {"status": "activity_missing", "central": None, "low": None, "high": None}
            elif factor is None:
                result = {"status": resolution["status"], "central": None, "low": None, "high": None}
            else:
                result = calculate_generated_load(activity, factor)
            treatment = treatment_by_key.get((source.source_id, pollutant))
            generated = result["central"]
            removed, net = (None, None) if generated is None else apply_treatment(float(generated), treatment)
            evidence_tier = _factor_evidence_tier(factor) if generated is not None else "unknown"
            record = PollutionLoadRecord(
                ledger_id="load_" + sha256(f"{source.source_id}:{pollutant}".encode()).hexdigest()[:12],
                source_id=source.source_id, source_type=source.source_type, pollutant=pollutant,
                generated_load=generated, removed_load=removed, net_emission_load=net,
                unit="kg/day", temporal_basis="daily_average", evidence_tier=evidence_tier,
                source_activity_id=activity.activity_id if activity else None,
                emission_factor_id=factor.factor_id if factor else None,
                treatment_id=treatment.treatment_id if treatment else None,
                uncertainty_low=result["low"], uncertainty_high=result["high"],
                uncertainty_status="available" if result["low"] is not None and result["high"] is not None else "unavailable",
                spatial_status=source.spatial_status, calculation_status=str(result["status"]),
                provenance={"source_inventory": source.source_id, "activity": activity.activity_id if activity else None, "factor": factor.factor_id if factor else None, "treatment": treatment.treatment_id if treatment else None},
            )
            rows.append(record.as_dict())
    return pd.DataFrame(rows)


def build_pollutant_availability_matrix(ledger: pd.DataFrame) -> pd.DataFrame:
    labels = {
        "calculated": "estimated", "measured": "measured",
        "emission_factor_missing": "factor_missing",
        "factor_not_approved_for_real_project": "factor_missing",
        "activity_missing": "activity_missing",
    }
    frame = ledger[["source_id", "pollutant", "calculation_status"]].copy()
    frame["availability"] = frame.calculation_status.map(labels).fillna("unknown")
    matrix = frame.pivot(index="source_id", columns="pollutant", values="availability").reset_index()
    matrix.columns.name = None
    for pollutant in POLLUTANTS:
        if pollutant not in matrix: matrix[pollutant] = "unknown"
    return matrix[["source_id", *POLLUTANTS]]


def validate_source_load_ledger(ledger: pd.DataFrame, tolerance: float = 1e-9) -> dict[str, Any]:
    quantified = ledger.dropna(subset=["generated_load", "removed_load", "net_emission_load"])
    residual = quantified.generated_load - quantified.removed_load - quantified.net_emission_load
    violations = quantified[(quantified.removed_load < -tolerance) | (quantified.removed_load - quantified.generated_load > tolerance)]
    maximum = float(residual.abs().max()) if len(residual) else 0.0
    return {"status": "passed" if maximum <= tolerance and violations.empty else "failed", "quantified_records": len(quantified), "unquantified_records": len(ledger) - len(quantified), "max_balance_residual_kg_day": maximum, "violation_count": len(violations), "semantic_scope": "generated_removed_net_emission_only"}


def summarize_source_loads(ledger: pd.DataFrame, sources: pd.DataFrame) -> dict[str, pd.DataFrame]:
    quantified = ledger.dropna(subset=["net_emission_load"])
    joined = ledger.merge(sources[["source_id", "subbasin_id", "administrative_unit"]], on="source_id", how="left")
    def summary(by: list[str]) -> pd.DataFrame:
        known = joined.dropna(subset=["net_emission_load"])
        values = known.groupby(by, dropna=False, as_index=False).agg(quantified_source_count=("source_id", "nunique"), generated_load_kg_day=("generated_load", "sum"), removed_load_kg_day=("removed_load", "sum"), net_emission_load_kg_day=("net_emission_load", "sum"))
        return values
    return {
        "by_source": summary(["source_type", "pollutant"]),
        "by_pollutant": summary(["pollutant"]),
        "by_subbasin": summary(["subbasin_id", "pollutant"]),
        "by_administrative_unit": summary(["administrative_unit", "pollutant"]),
        "quantified": quantified,
    }


def assess_pollutant_delivery_model_gate(coverage: dict[str, Any], hydrology_gate: str) -> dict[str, Any]:
    activity_blockers = ["insufficient_quantified_source_coverage"] if coverage["quantified_source_fraction"] < coverage.get("minimum_source_coverage", 0.8) else []
    factor_blockers = ["approved_emission_factors_missing"] if coverage["missing_factor_count"] > 0 else []
    spatial_blockers = []
    if coverage["spatial_coverage"] < coverage.get("minimum_spatial_coverage", 0.8): spatial_blockers.append("insufficient_spatial_coverage")
    if coverage.get("reach_coverage", 0.0) < coverage.get("minimum_reach_coverage", 0.8): spatial_blockers.append("insufficient_reach_mapping")
    if coverage.get("low_confidence_spatial_count", 0) > 0: spatial_blockers.append("low_confidence_spatial_attribution")
    hydrology_blockers = ["hydrology_gate_blocked"] if hydrology_gate == "blocked" else []
    blockers = activity_blockers + factor_blockers + spatial_blockers + hydrology_blockers
    warnings = [] if hydrology_gate == "ready" else ["hydrology_ready_with_warnings"]
    status = "blocked" if blockers else "ready_with_warnings" if warnings else "ready"
    return {"status": status, "blockers": blockers, "warnings": warnings, "activity_blockers": activity_blockers, "factor_blockers": factor_blockers, "spatial_blockers": spatial_blockers, "hydrology_blockers": hydrology_blockers, "hydrology_gate": hydrology_gate}
