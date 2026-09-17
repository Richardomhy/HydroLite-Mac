"""Confirmed measured/reported source emissions take priority over generated estimates."""

import pandas as pd

from hydrolite.source_evidence import evidence_errors, evidence_to_activity
from hydrolite.source_load_ledger import build_source_load_ledger, calculate_measured_load
from hydrolite.unit_system import convert_unit


def build_evidence_ledger(sources, evidence, approved_factors):
    activities = [a for e in evidence if (a := evidence_to_activity(e)) is not None]
    # Conflicting activities are unresolved rather than silently taking the last row.
    counts = pd.Series([a.source_id for a in activities], dtype=str).value_counts()
    usable = [a for a in activities if counts[a.source_id] == 1]
    keys = [(f.source_type, f.pollutant) for f in approved_factors]
    unambiguous_factors = [f for f in approved_factors if keys.count((f.source_type, f.pollutant)) == 1]
    ledger = build_source_load_ledger(sources, usable, unambiguous_factors)
    ledger["ledger_version"] = 2
    ledger["load_basis"] = "generated_estimate"
    confirmed = [e for e in evidence if e.status == "confirmed" and e.approved and e.approved_by and e.approved_at and not evidence_errors(e, quantitative=True)]
    for index, row in ledger.iterrows():
        if sources.loc[sources.source_id.eq(row.source_id), "status"].iloc[0] != "accepted":
            ledger.loc[index, ["generated_load", "removed_load", "net_emission_load"]] = None
            ledger.loc[index, "calculation_status"] = "source_confirmation_required"; continue
        candidates = [e for e in confirmed if e.source_id == row.source_id]
        concentrations = [e for e in candidates if e.evidence_type == "measured_concentration" and e.pollutant == row.pollutant and e.measurement_role in {"effluent", "outfall"}]
        pairs = [(c, f) for c in concentrations for f in candidates if f.evidence_type in {"discharge_flow", "wastewater_volume"} and c.date_start == f.date_start and c.date_end == f.date_end and c.temporal_basis == f.temporal_basis and f.measurement_role in {"effluent", "outfall"}]
        load, basis, ids, tier = None, "", [], ""
        if len(pairs) == 1:
            c, f = pairs[0]
            try:
                flow = float(convert_unit([f.extracted_value], f.unit, "m3/s").normalized_value.iloc[0]) if f.evidence_type == "discharge_flow" else float(convert_unit([f.extracted_value], f.unit, "m3").normalized_value.iloc[0]) / (pd.Timestamp(f.date_end) - pd.Timestamp(f.date_start)).total_seconds()
                concentration = float(convert_unit([c.extracted_value], c.unit, "mg/l").normalized_value.iloc[0])
                load = calculate_measured_load(concentration, flow)["load_kg_day"]
                basis, ids, tier = "measured_source_emission", [c.evidence_id, f.evidence_id], "evidence_tier_1"
            except (ValueError, ZeroDivisionError): pass
        reports = [e for e in candidates if e.evidence_type == "reported_pollutant_load" and e.pollutant == row.pollutant and e.provenance.get("reporting_authority") and e.provenance.get("load_scope") == "source_emission"]
        if load is None and len(reports) == 1:
            report = reports[0]
            try:
                load = float(convert_unit([report.extracted_value], report.unit, "kg/day").normalized_value.iloc[0])
                basis, ids, tier = "reported_source_emission", [report.evidence_id], "evidence_tier_2"
            except ValueError: pass
        if load is not None:
            # Effluent observations do not reveal generated load or treatment removal.
            ledger.loc[index, ["generated_load", "removed_load"]] = None
            ledger.loc[index, "net_emission_load"] = load
            ledger.loc[index, "load_basis"] = basis
            ledger.loc[index, "calculation_status"] = "measured" if tier == "evidence_tier_1" else "reported"
            ledger.loc[index, "evidence_tier"] = tier
            ledger.loc[index, ["emission_factor_id", "treatment_id", "uncertainty_low", "uncertainty_high"]] = None
            ledger.at[index, "provenance"] = {"evidence_ids": ids, "scope": "source_emission_only", "not_generated_load": True}
            basis_evidence = pairs[0][0] if tier == "evidence_tier_1" else reports[0]
            ledger.loc[index, "temporal_basis"] = basis_evidence.temporal_basis
            ledger.loc[index, "date_start"] = basis_evidence.date_start
            ledger.loc[index, "date_end"] = basis_evidence.date_end
    return ledger, activities
