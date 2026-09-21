"""Point-source evidence audit; no inferred emissions or project approvals."""

from dataclasses import dataclass
import json
import math

import pandas as pd

from hydrolite.source_evidence import evidence_errors
from hydrolite.water_environment_contracts import Record, POLLUTANTS


@dataclass(frozen=True)
class PointSourceEvidenceClosure(Record):
    source_id: str
    identity_status: str = "ambiguous"
    coordinate_status: str = "unknown"
    coordinate_crs: str = ""
    coordinate_confidence: str = "low"
    receiving_water_status: str = "missing"
    receiving_water_name: str = ""
    reach_id: str = ""
    reach_mapping_method: str = "unresolved"
    reach_mapping_confidence: str = "unresolved"
    flow_status: str = "missing"
    flow_evidence_id: str = ""
    wastewater_volume_status: str = "missing"
    concentration_status: str = "missing"
    pollutants_available: str = ""
    reported_load_status: str = "missing"
    measured_load_status: str = "missing"
    factor_required: bool = True
    factor_status: str = "decision_required"
    temporal_alignment_status: str = "unknown"
    evidence_completeness: str = "incomplete"
    blocker_codes: str = ""
    next_action: str = "Supply source-specific evidence"


def context_dict(e):
    value = e.provenance.get("context", {})
    if isinstance(value, dict): return value
    try: return json.loads(value)
    except (ValueError, TypeError): return {"text": str(value)}


def audit_source_identity(sources):
    duplicate_ids = set(sources.loc[sources.source_id.duplicated(False), "source_id"])
    duplicate_names = set(sources.loc[sources.name.duplicated(False), "name"])
    rows = []
    for s in sources.to_dict("records"):
        status = "confirmed" if s["status"] == "accepted" and s.get("provenance") else "probable"
        if not s.get("source_id") or not s.get("name"): status = "ambiguous"
        if s["source_id"] in duplicate_ids: status = "conflicting"
        elif s["name"] in duplicate_names: status = "ambiguous"
        rows.append({"source_id": s["source_id"], "name": s["name"], "source_type": s["source_type"], "identity_status": status, "original_dataset": str(s.get("provenance", "")), "duplicate_identity": s["source_id"] in duplicate_ids, "alias": "", "coordinate_record": s.get("geometry_reference", "")})
    return pd.DataFrame(rows)


def approved_numeric(e):
    return e.status == "confirmed" and e.approved and bool(e.approved_by and e.approved_at) and not evidence_errors(e, quantitative=True)


def classify_flow(e):
    if e.evidence_type == "treatment_capacity": return "design_capacity"
    text = (e.field_name + " " + e.measurement_role).lower()
    if any(t in text for t in ("设计", "design", "capacity", "处理规模")): return "design_capacity"
    if any(t in text for t in ("许可", "permitted")): return "permitted_capacity"
    if any(t in text for t in ("估算", "estimated")): return "estimated_flow"
    if e.provenance.get("flow_kind") in {"measured_flow", "reported_actual_flow"}: return e.provenance["flow_kind"]
    if any(t in text for t in ("实测", "measured")): return "measured_flow"
    if any(t in text for t in ("实际", "reported_actual")): return "reported_actual_flow"
    return "unknown_flow_context"


def concentration_context(e):
    role = e.measurement_role
    explicit = {"outfall_effluent", "wwtp_influent", "wwtp_effluent", "river_water"}
    if role in explicit: return role
    header = e.field_name.lower()
    if "进水" in header or role == "influent": return "wwtp_influent"
    if "出水" in header: return "wwtp_effluent"
    context = context_dict(e)
    if "排污口名称" in context and role in {"outfall", "effluent"}: return "outfall_effluent"
    if any("河道" in str(k) or "断面" in str(k) for k in context): return "river_water"
    return "unknown_context"


def audit_concentrations(evidence):
    rows = []
    for e in evidence:
        if e.evidence_type != "measured_concentration" or e.status in {"superseded", "rejected", "external_evidence_missing"}: continue
        value = str(e.extracted_value)
        qualifier = next((x for x in ("<", ">", "≤", "≥", "未检出", "ND") if x in value), "")
        rows.append({"evidence_id": e.evidence_id, "source_id": e.source_id, "pollutant": e.pollutant, "value": e.extracted_value, "unit": e.unit, "date_start": e.date_start, "date_end": e.date_end, "context": concentration_context(e), "qualifier": qualifier, "confirmed": approved_numeric(e), "file_reference": e.file_reference})
    frame = pd.DataFrame(rows, columns=["evidence_id", "source_id", "pollutant", "value", "unit", "date_start", "date_end", "context", "qualifier", "confirmed", "file_reference"])
    frame["duplicate"] = frame.duplicated(["source_id", "pollutant", "date_start", "date_end", "context"], keep=False)
    frame["usable"] = frame.confirmed & ~frame.duplicate & frame.qualifier.eq("") & frame.context.isin(["outfall_effluent", "wwtp_effluent"]) & frame.pollutant.isin(POLLUTANTS) & frame.source_id.ne("")
    return frame


def temporal_alignment(flow, concentration):
    try:
        if not all([flow.date_start, flow.date_end, concentration.date_start, concentration.date_end]): return "unknown"
        a, b, c, d = [pd.Timestamp(x) for x in (flow.date_start, flow.date_end, concentration.date_start, concentration.date_end)]
        if any(pd.isna(x) for x in (a, b, c, d)) or b < a or d < c: return "unknown"
        if a == c and b == d and flow.temporal_basis == concentration.temporal_basis: return "exact"
        if a.normalize() == b.normalize() == c.normalize() == d.normalize(): return "same_day"
        if b < c or d < a: return "non_overlapping"
        return "same_period"
    except (ValueError, TypeError): return "unknown"


def factor_decision_records(factors, approvals, project_id):
    from hydrolite.emission_factor_approval import approved_project_factors, factor_stage
    approved = {f.factor_id for f in approved_project_factors(factors, approvals, project_id)}
    rows = []
    for f in factors:
        if f.example: continue
        incompatible = f.source_type not in {"direct_outfall", "wastewater_treatment"}
        recommendation = "recommend_reject" if factor_stage(f) != "generation_factor" else "recommend_need_more_evidence"
        rows.append({"factor_id": f.factor_id, "source": f.source_reference, "issuing_body": f.evidence.get("issuer"), "year": f.evidence.get("year"), "source_category": f.source_type, "pollutant": f.pollutant, "stage": factor_stage(f), "value": f.value, "unit": f.numerator_unit + "/" + f.denominator_unit, "region_applicability": f.region_applicability, "project_applicability": "not_a_point_source_factor" if incompatible else "activity_and_project_review_required", "conflict_with_other_factors": ";".join(x.factor_id for x in factors if x.factor_id != f.factor_id and not x.example and (x.source_type, x.pollutant) == (f.source_type, f.pollutant)), "recommended_decision": recommendation, "decision_rationale": "Do not substitute population-generation factors for outfall observations; confirm region, activity and scope. COD is not CODMn.", "reviewer_action_required": f.factor_id not in approved, "project_status": "approved_for_project" if f.factor_id in approved else "decision_required"})
    return pd.DataFrame(rows)
