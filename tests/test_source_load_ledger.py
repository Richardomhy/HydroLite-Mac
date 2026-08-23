from __future__ import annotations

import math

import pandas as pd
import pytest

from hydrolite.emission_factor_registry import load_emission_factors, resolve_emission_factor
from hydrolite.source_load_ledger import (
    assess_pollutant_delivery_model_gate, build_pollutant_availability_matrix,
    build_source_load_ledger, calculate_generated_load, calculate_measured_load,
    validate_activity_record, validate_source_load_ledger, validate_treatment_factor,
)
from hydrolite.water_environment_contracts import ActivityRecord, EmissionFactor, TreatmentFactor


def _activity(value=365.25):
    return ActivityRecord("a1", "s1", "population", value, "person", "2026-01-01", "2026-12-31", "annual_average", "d1", "population", "observed", "reviewed", {"row": 1})


def _factor(**overrides):
    values = dict(factor_id="f1", source_type="rural_domestic", pollutant="TN", value=1.0, numerator_unit="kg/year", denominator_unit="person", temporal_basis="annual", region_applicability="test", source_reference="anonymous official fixture", source_type_reference="local_official", confidence="medium", uncertainty_low=0.8, uncertainty_high=1.2, valid_from="", valid_to="", notes="", approved_for_real_project=True, example=False)
    values.update(overrides); return EmissionFactor(**values)


def test_generated_load_units_uncertainty_and_measured_priority():
    result = calculate_generated_load(_activity(), _factor())
    assert result["status"] == "calculated" and math.isclose(result["central"], 1.0)
    assert result["low"] == pytest.approx(0.8) and result["high"] == pytest.approx(1.2)
    measured = calculate_measured_load(2.0, 1.0)
    assert measured["load_kg_day"] == pytest.approx(172.8)
    assert measured["evidence_tier"] == "evidence_tier_1"


def test_ledger_balance_treatment_and_semantic_matrix():
    sources = pd.DataFrame([{"source_id": "s1", "source_type": "rural_domestic", "status": "accepted", "spatial_status": "mapped"}])
    treatment = TreatmentFactor("t1", "s1", "TN", 0.25, "anonymous", None, 0.8, "fixture", "medium")
    ledger = build_source_load_ledger(sources, [_activity()], [_factor()], [treatment])
    row = ledger.loc[ledger.pollutant.eq("TN")].iloc[0]
    assert row.generated_load == pytest.approx(1.0)
    assert row.removed_load == pytest.approx(0.2)
    assert row.net_emission_load == pytest.approx(0.8)
    assert row.evidence_tier == "evidence_tier_3"
    assert validate_source_load_ledger(ledger)["status"] == "passed"
    matrix = build_pollutant_availability_matrix(ledger)
    assert matrix.loc[0, "TN"] == "estimated" and matrix.loc[0, "TP"] == "factor_missing"


def test_invalid_activity_treatment_and_example_factor_gate():
    assert validate_activity_record(_activity(-1))["status"] == "failed"
    invalid = TreatmentFactor("t1", "s1", "TN", 1.1, "anonymous", None, None, "fixture", "low")
    assert validate_treatment_factor(invalid)["status"] == "failed"
    factors = load_emission_factors("config/water_environment/emission_factors.example.yaml")
    result = resolve_emission_factor(factors, "direct_outfall", "TN", real_project=True)
    assert result["status"] == "factor_not_approved_for_real_project" and result["factor"] is None


def test_delivery_gate_blocks_missing_factors_and_reach_mapping():
    coverage = {"quantified_source_fraction": 0.0, "spatial_coverage": 1.0, "reach_coverage": 0.0, "missing_factor_count": 4, "minimum_source_coverage": 0.8, "minimum_spatial_coverage": 0.8, "minimum_reach_coverage": 0.8}
    gate = assess_pollutant_delivery_model_gate(coverage, "ready_with_warnings")
    assert gate["status"] == "blocked"
    assert {"insufficient_quantified_source_coverage", "approved_emission_factors_missing", "insufficient_reach_mapping"} <= set(gate["blockers"])
