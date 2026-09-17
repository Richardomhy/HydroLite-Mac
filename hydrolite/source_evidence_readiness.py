"""Unchanged 80% gates and explicit category gaps, not basin-total extrapolation."""

import pandas as pd

from hydrolite.source_load_ledger import assess_pollutant_delivery_model_gate
from hydrolite.water_environment_contracts import POLLUTANTS

CATEGORIES = {"point_sources": {"direct_outfall", "wastewater_treatment"}, "domestic": {"rural_domestic", "municipal_domestic"}, "industrial": {"industrial"}, "livestock": {"pig", "cattle", "poultry", "other_livestock"}, "crop_agriculture": {"crop_agriculture", "orchard", "fertilizer_application"}, "aquaculture": {"pond_aquaculture", "lake_aquaculture", "intensive_aquaculture"}}


def evaluate_evidence_readiness(sources, evidence, activities, factors, mapping, ledger, hydrology_gate):
    activity_ids = {a.source_id for a in activities}
    evidence_ids = {e.source_id for e in evidence if e.source_id and e.status != "rejected"}
    rows = [{"source_id": s.source_id, "source_type": s.source_type, "status": "activity_ready" if s.source_id in activity_ids else "activity_partial" if s.source_id in evidence_ids else "activity_missing"} for s in sources.itertuples()]
    category_rows, gates = [], {}
    for category, types in CATEGORIES.items():
        ids = set(sources.loc[sources.source_type.isin(types), "source_id"])
        subset = ledger[ledger.source_id.isin(ids)]
        known = subset[subset.net_emission_load.notna()]
        category_rows.append({"category": category, "sources": len(ids), "quantified_sources": known.source_id.nunique(), "status": "unknown" if not ids else "complete" if len(known) == len(ids) * len(POLLUTANTS) else "partial" if len(known) else "missing"})
    for group, types in (("point_source", CATEGORIES["point_sources"]), ("diffuse_source", set.union(*[t for c, t in CATEGORIES.items() if c != "point_sources"]))):
        ids = set(sources.loc[sources.source_type.isin(types), "source_id"]); n = len(ids)
        subset = ledger[ledger.source_id.isin(ids)]
        mapped = mapping[mapping.source_id.isin(ids)]
        quantified = subset[subset.net_emission_load.notna()]
        missing_factor = sum(not any(f.source_type == r.source_type and f.pollutant == r.pollutant for f in factors) for r in subset[subset.net_emission_load.isna()].itertuples())
        coverage = {"quantified_source_fraction": quantified.source_id.nunique() / n if n else 0, "missing_factor_count": missing_factor, "spatial_coverage": mapped.subbasin_id.notna().sum() / n if n else 0, "reach_coverage": (mapped.reach_id.notna() & mapped.confidence.isin(["high", "medium"])).sum() / n if n else 0, "low_confidence_spatial_count": int((~mapped.confidence.isin(["high", "medium"]) | ~mapped.subbasin_confidence.isin(["high", "medium"])).sum()), "minimum_source_coverage": 0.8, "minimum_spatial_coverage": 0.8, "minimum_reach_coverage": 0.8}
        gate = assess_pollutant_delivery_model_gate(coverage, hydrology_gate)
        if not n or sources.loc[sources.source_id.isin(ids), "status"].ne("accepted").any(): gate["blockers"].append("source_inventory_incomplete")
        if not len(quantified): gate["blockers"].append("no_usable_source_load")
        if hydrology_gate not in {"ready", "ready_with_warnings"}: gate["blockers"].append("hydrology_not_ready")
        if gate["blockers"]: gate["status"] = "blocked"
        gate["coverage"] = coverage; gates[group + "_delivery_gate"] = gate
    # Overall remains blocked until both domains are ready; a future point-only task needs explicit scope.
    gates["pollutant_delivery_model_gate"] = "blocked" if any(g["status"] == "blocked" for g in gates.values()) else "ready_with_warnings" if hydrology_gate != "ready" else "ready"
    gates["overall_rule"] = "both_point_and_diffuse_required; thresholds unchanged from M9A"
    gates["basin_total_status"] = "reportable" if all(c["status"] == "complete" for c in category_rows) else "not_reportable"
    return gates, pd.DataFrame(rows), pd.DataFrame(category_rows)


def build_data_requests() -> pd.DataFrame:
    fields = {
        "point_sources": [("source_id", "identifier"), ("coordinates_crs", "degrees/EPSG"), ("receiving_water_reach_crosswalk", "reach_id"), ("discharge_flow_or_volume", "m3/s or m3/period"), *[(p, "mg/L") for p in POLLUTANTS], ("monitoring_period", "ISO8601"), ("operating_condition", "text")],
        "domestic": [("village", "identifier"), ("population", "person"), ("sewage_generation", "m3/day"), ("treatment_mode", "text"), ("treatment_coverage", "fraction"), ("discharge_destination", "reach_id")],
        "livestock": [("farm_area", "identifier"), ("species", "text"), ("head_count_or_production", "head/period"), ("manure_treatment", "text"), ("discharge", "m3/period"), ("location", "coordinates/CRS")],
        "crop_agriculture": [("crop_area", "ha"), ("crop_type", "text"), ("fertilizer_N", "kg/period"), ("fertilizer_P", "kg/period"), ("application_period", "ISO8601")],
        "aquaculture": [("area", "ha"), ("production", "kg/period"), ("feed", "kg/period"), ("water_exchange_drainage", "m3/period"), ("tailwater_treatment", "text"), ("discharge_period", "ISO8601")],
        "industrial": [("industry_process", "text"), ("actual_production", "kg/period"), ("permit_source_emission", "kg/day"), ("location", "coordinates/CRS")],
        "factor_approval": [("generation_factor_evidence_and_project_decision", "kg/day/activity unit")],
    }
    return pd.DataFrame([{"data_category": category, "required_field": name, "unit": unit, "temporal_coverage": "same documented period as paired evidence", "spatial_coverage": "source-level, not county total", "priority": "P1" if name in {"operating_condition", "treatment_mode", "crop_type", "species", "feed"} else "P0", "why_needed": "Resolve source identity, activity, factor or spatial provenance", "calculation_blocked": "source emission accounting / downstream readiness", "acceptable_alternative_evidence": "signed monitoring/operation record with source ID, period, units and document reference", "example_format": f"source_id=anonymous_01; field={name}; value=<verified>; unit={unit}; start=<date>; end=<date>; document=<reference>"} for category, values in fields.items() for name, unit in values])
