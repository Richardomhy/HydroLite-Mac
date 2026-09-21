"""Same-source observation matching; all alternatives retained for audit."""

import pandas as pd

from hydrolite.point_source_evidence import approved_numeric, classify_flow, temporal_alignment, audit_concentrations
from hydrolite.source_evidence_ledger import build_evidence_ledger
from hydrolite.source_load_ledger import calculate_measured_load
from hydrolite.unit_system import convert_unit, validate_unit_compatibility


def point_source_loads(sources, identity, evidence, factors):
    concentrations = audit_concentrations(evidence)
    by_id = {e.evidence_id: e for e in evidence}
    good_ids = set(identity.loc[identity.identity_status.eq("confirmed"), "source_id"])
    concentrations["usable"] &= concentrations.source_id.isin(good_ids)
    active = [e for e in evidence if e.status not in {"rejected", "superseded", "external_evidence_missing"}]
    flow = pd.DataFrame([{"evidence_id": e.evidence_id, "source_id": e.source_id, "kind": classify_flow(e), "evidence_type": e.evidence_type, "value": e.extracted_value, "unit": e.unit, "date_start": e.date_start, "date_end": e.date_end, "usable": approved_numeric(e) and e.source_id in good_ids and classify_flow(e) in {"measured_flow", "reported_actual_flow"}, "match_method": e.provenance.get("identity_rule", "documented_source_id"), "confidence": e.confidence} for e in active if e.evidence_type in {"discharge_flow", "wastewater_volume", "treatment_capacity"}], columns=["evidence_id", "source_id", "kind", "evidence_type", "value", "unit", "date_start", "date_end", "usable", "match_method", "confidence"])
    matches, observations = [], []
    for c in concentrations.itertuples():
        if not c.usable or c.source_id not in good_ids: continue
        for f in flow.loc[flow.source_id.eq(c.source_id)].itertuples():
            ce, fe = by_id[c.evidence_id], by_id[f.evidence_id]
            alignment = temporal_alignment(fe, ce)
            row = {"source_id": c.source_id, "pollutant": c.pollutant, "concentration_evidence_id": c.evidence_id, "flow_evidence_id": f.evidence_id, "temporal_alignment": alignment, "load_kg_day": None, "status": "blocked", "date_start": ce.date_start, "date_end": ce.date_end}
            if f.usable and alignment in {"exact", "same_day"}:
                try:
                    if validate_unit_compatibility(fe.unit, "m3/s")["compatible"]:
                        q = convert_unit([fe.extracted_value], fe.unit, "m3/s").normalized_value.iloc[0]
                    else:
                        seconds = (pd.Timestamp(fe.date_end) - pd.Timestamp(fe.date_start)).total_seconds()
                        if seconds <= 0 or alignment != "exact": raise ValueError("Explicit matching volume period required")
                        q = convert_unit([fe.extracted_value], fe.unit, "m3").normalized_value.iloc[0] / seconds
                    mg = convert_unit([ce.extracted_value], ce.unit, "mg/l").normalized_value.iloc[0]
                    row.update(load_kg_day=calculate_measured_load(mg, q)["load_kg_day"], status="measured")
                except (ValueError, TypeError): pass
            matches.append(row)
    for e in active:
        if e.evidence_type != "reported_pollutant_load": continue
        row = {"source_id": e.source_id, "pollutant": e.pollutant, "evidence_id": e.evidence_id, "date_start": e.date_start, "date_end": e.date_end, "load_kg_day": None, "status": "blocked"}
        if e.source_id in good_ids and approved_numeric(e) and e.provenance.get("reporting_authority") and e.provenance.get("load_scope") == "source_emission":
            try: row.update(load_kg_day=float(convert_unit([e.extracted_value], e.unit, "kg/day").normalized_value.iloc[0]), status="reported")
            except ValueError: pass
        observations.append(row)
    alignment = pd.DataFrame(matches, columns=["source_id", "pollutant", "concentration_evidence_id", "flow_evidence_id", "temporal_alignment", "load_kg_day", "status", "date_start", "date_end"])
    reports = pd.DataFrame(observations, columns=["source_id", "pollutant", "evidence_id", "date_start", "date_end", "load_kg_day", "status"])
    # Exclude measured/reported evidence from legacy precedence: preserve both here.
    ledger, _ = build_evidence_ledger(sources, [e for e in active if e.evidence_type not in {"measured_concentration", "reported_pollutant_load", "discharge_flow", "wastewater_volume", "treatment_capacity"}], factors)
    ledger["ledger_version"] = 3
    comparisons = []
    for index, r in ledger.iterrows():
        measured = alignment[alignment.source_id.eq(r.source_id) & alignment.pollutant.eq(r.pollutant) & alignment.status.eq("measured")]
        reported = reports[reports.source_id.eq(r.source_id) & reports.pollutant.eq(r.pollutant) & reports.status.eq("reported")]
        comparison = {"source_id": r.source_id, "pollutant": r.pollutant, "status": "not_comparable", "absolute_difference_kg_day": None, "relative_difference": None}
        if len(measured) == len(reported) == 1:
            m, p = measured.iloc[0], reported.iloc[0]
            comparison.update(measured_kg_day=m.load_kg_day, reported_kg_day=p.load_kg_day)
            if m.date_start == p.date_start and m.date_end == p.date_end:
                delta = abs(m.load_kg_day - p.load_kg_day); ratio = delta / max(abs(m.load_kg_day), abs(p.load_kg_day), 1e-12)
                comparison.update(absolute_difference_kg_day=delta, relative_difference=ratio, status="consistent" if ratio <= .2 else "material_disagreement")
            else: comparison["status"] = "different_period"
        comparisons.append(comparison)
        selected = measured if len(measured) == 1 else reported if len(measured) == 0 and len(reported) == 1 else pd.DataFrame()
        if comparison["status"] == "material_disagreement": selected = pd.DataFrame()
        if len(selected) == 1 and r.source_id in good_ids:
            obs = selected.iloc[0]
            ledger.loc[index, ["generated_load", "removed_load", "emission_factor_id", "treatment_id", "uncertainty_low", "uncertainty_high"]] = None
            ledger.loc[index, "net_emission_load"] = obs.load_kg_day
            ledger.loc[index, "calculation_status"] = obs.status
            ledger.loc[index, "load_basis"] = obs.status + "_source_emission"
            ledger.loc[index, "evidence_tier"] = "evidence_tier_1" if obs.status == "measured" else "evidence_tier_2"
            ledger.loc[index, "date_start"] = obs.date_start; ledger.loc[index, "date_end"] = obs.date_end
            ledger.at[index, "provenance"] = obs.to_dict()
        elif r.source_id not in good_ids or len(measured) > 1 or len(reported) > 1 or comparison["status"] == "material_disagreement":
            ledger.loc[index, ["generated_load", "removed_load", "net_emission_load"]] = None
            ledger.loc[index, "calculation_status"] = "evidence_conflict_or_identity_unresolved"
    return ledger, flow, concentrations, alignment, reports, pd.DataFrame(comparisons)
