"""Point-only eligibility is never basin-wide readiness."""

import pandas as pd

from hydrolite.point_source_evidence import PointSourceEvidenceClosure
from hydrolite.water_environment_contracts import POLLUTANTS

DEFAULT_THRESHOLDS = {"minimum_identity_coverage": .8, "minimum_quantified_coverage": .8, "minimum_spatial_coverage": .8, "minimum_category_coverage": .8, "near_distance_m": 100.0}


def point_source_readiness(sources, identity, coordinates, mapping, flow, concentration, alignment, ledger, factors, *, thresholds=None, hydrology_gate="ready_with_warnings"):
    config = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    for k, v in config.items():
        if k.startswith("minimum_") and not .8 <= float(v) <= 1: raise ValueError("Coverage thresholds cannot be reduced below M9A 80%")
    rows = []
    for s in sources.itertuples():
        i = identity[identity.source_id.eq(s.source_id)].iloc[0]
        c = coordinates[coordinates.source_id.eq(s.source_id)].iloc[0]
        m = mapping[mapping.source_id.eq(s.source_id)].iloc[0]
        f = flow[flow.source_id.eq(s.source_id) & flow.usable.eq(True)]
        con = concentration[concentration.source_id.eq(s.source_id) & concentration.usable.eq(True)]
        loads = ledger[ledger.source_id.eq(s.source_id)]
        quantified = set(loads.loc[loads.net_emission_load.notna(), "pollutant"])
        missing_factors = [p for p in POLLUTANTS if p not in quantified and not any(x.source_type == s.source_type and x.pollutant == p for x in factors)]
        blockers = []
        if i.identity_status != "confirmed": blockers.append("identity_unconfirmed")
        if c.coordinate_status != "confirmed": blockers.append("coordinate_unconfirmed")
        if not m.reach_confirmed: blockers.append("reach_unconfirmed")
        if not quantified: blockers.append("load_missing")
        if len(quantified) < len(POLLUTANTS): blockers.append("pollutant_coverage_incomplete")
        aligned = alignment[alignment.source_id.eq(s.source_id)]
        rows.append(PointSourceEvidenceClosure(source_id=s.source_id, identity_status=i.identity_status, coordinate_status=c.coordinate_status, coordinate_crs=c.coordinate_crs, coordinate_confidence=c.confidence, receiving_water_status="documented" if m.receiving_water else "missing", receiving_water_name=m.receiving_water, reach_id=m.reach_id or "", reach_mapping_method=m.mapping_method, reach_mapping_confidence=m.confidence, flow_status="ready" if len(f) else "missing", flow_evidence_id=";".join(f.evidence_id), wastewater_volume_status="ready" if f.evidence_type.eq("wastewater_volume").any() else "missing", concentration_status="ready" if len(con) else "missing", pollutants_available=";".join(sorted(set(con.pollutant))), reported_load_status="ready" if loads.calculation_status.eq("reported").any() else "missing", measured_load_status="ready" if loads.calculation_status.eq("measured").any() else "missing", factor_required=len(quantified) < len(POLLUTANTS), factor_status="not_required" if len(quantified) == len(POLLUTANTS) else "decision_required" if missing_factors else "approved", temporal_alignment_status=";".join(sorted(set(aligned.temporal_alignment))) or "unknown", evidence_completeness="complete" if not blockers else "incomplete", blocker_codes=";".join(blockers), next_action="Close: " + ";".join(blockers)).as_dict())
    closure = pd.DataFrame(rows); n = len(closure)
    fraction = lambda mask: float(mask.sum() / n) if n else 0.0
    quantified_ids = set(ledger.loc[ledger.net_emission_load.notna(), "source_id"])
    complete_ids = {sid for sid, group in ledger.groupby("source_id") if set(group.loc[group.net_emission_load.notna(), "pollutant"]) >= set(POLLUTANTS)}
    joint_ids = complete_ids & set(mapping.loc[mapping.reach_confirmed, "source_id"]) & set(identity.loc[identity.identity_status.eq("confirmed"), "source_id"])
    coverage = {"source_identity_coverage": fraction(closure.identity_status.eq("confirmed")), "coordinate_confirmed_coverage": fraction(closure.coordinate_status.eq("confirmed")), "subbasin_mapping_coverage": fraction(mapping.subbasin_id.notna()), "reach_mapping_coverage": fraction(mapping.reach_confirmed), "medium_or_high_reach_coverage": fraction(mapping.reach_confirmed & mapping.confidence.isin(["medium", "high"])), "flow_evidence_coverage": fraction(closure.flow_status.eq("ready")), "concentration_evidence_coverage": fraction(closure.concentration_status.eq("ready")), "measured_load_ready_coverage": fraction(closure.measured_load_status.eq("ready")), "reported_load_coverage": fraction(closure.reported_load_status.eq("ready")), "quantified_load_coverage": len(quantified_ids) / n if n else 0, "all_pollutants_quantified_coverage": len(complete_ids) / n if n else 0, "joint_load_spatial_coverage": len(joint_ids) / n if n else 0, "importance_weighted_coverage": "unavailable"}
    categories = {kind: len(set(group.source_id) & joint_ids) / len(group) for kind, group in sources.groupby("source_type")}
    blockers = []
    if not n or coverage["source_identity_coverage"] < config["minimum_identity_coverage"]: blockers.append("identity_coverage")
    if coverage["medium_or_high_reach_coverage"] < config["minimum_spatial_coverage"]: blockers.append("spatial_coverage")
    if not joint_ids or coverage["joint_load_spatial_coverage"] < config["minimum_quantified_coverage"]: blockers.append("joint_load_spatial_coverage")
    if not categories or any(v < config["minimum_category_coverage"] for v in categories.values()): blockers.append("category_incomplete")
    if hydrology_gate not in {"ready", "ready_with_warnings"}: blockers.append("hydrology_blocked")
    if "importance_weight" in sources:
        weights = pd.to_numeric(sources.importance_weight, errors="coerce")
        if weights.isna().any() or (weights <= 0).any(): blockers.append("importance_weights_invalid")
        else:
            coverage["importance_weighted_coverage"] = float(weights[sources.source_id.isin(joint_ids)].sum() / weights.sum())
            if coverage["importance_weighted_coverage"] < config["minimum_quantified_coverage"]: blockers.append("important_sources_unresolved")
    gate = lambda ok: "ready" if ok else "blocked"
    gates = {"point_source_identity_gate": gate(coverage["source_identity_coverage"] >= config["minimum_identity_coverage"]), "point_source_spatial_gate": gate(coverage["medium_or_high_reach_coverage"] >= config["minimum_spatial_coverage"]), "point_source_flow_gate": gate(coverage["flow_evidence_coverage"] >= config["minimum_quantified_coverage"]), "point_source_concentration_gate": gate(coverage["concentration_evidence_coverage"] >= config["minimum_quantified_coverage"]), "point_source_factor_gate": gate(not closure.factor_status.eq("decision_required").any()), "point_source_load_gate": gate(bool(complete_ids) and coverage["all_pollutants_quantified_coverage"] >= config["minimum_quantified_coverage"]), "point_source_delivery_gate": "blocked" if blockers else "ready_with_warnings", "point_source_m9b_eligibility": "not_eligible" if blockers else "eligible_with_warnings", "diffuse_source_delivery_gate": "blocked", "pollutant_delivery_model_gate": "blocked", "blockers": blockers, "warnings": ["hydrology_" + hydrology_gate, "importance_weighted_coverage_unavailable"] if coverage["importance_weighted_coverage"] == "unavailable" else ["hydrology_" + hydrology_gate], "category_coverage": categories, "thresholds": config, "water_quality": "planned", "basin_total_status": "not_reportable"}
    return closure, coverage, gates
