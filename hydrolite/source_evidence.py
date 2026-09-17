"""Source-level evidence, review and activity conversion. No inferred activity values."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
import math
from typing import Any

import pandas as pd

from hydrolite.unit_system import convert_unit, validate_unit_compatibility
from hydrolite.water_environment_contracts import ActivityRecord, Record

EVIDENCE_TYPES = frozenset("location source_type discharge_flow wastewater_volume population livestock_count farm_capacity cropland_area fertilizer_application aquaculture_area aquaculture_production industrial_activity measured_concentration reported_pollutant_load treatment_capacity treatment_efficiency receiving_water outfall_to_reach_relation other".split())
ACTIVITY_UNITS = {"discharge_flow": "m3/s", "wastewater_volume": "m3", "population": "person", "livestock_count": "head", "cropland_area": "ha", "aquaculture_area": "ha", "fertilizer_application": "kg", "aquaculture_production": "kg", "industrial_activity": "kg"}


@dataclass(frozen=True, slots=True)
class SourceEvidenceRecord(Record):
    evidence_id: str
    source_id: str
    evidence_type: str
    dataset_id: str = ""
    document_id: str = ""
    file_reference: str = ""
    sheet_name: str = ""
    table_name: str = ""
    row_reference: str = ""
    field_name: str = ""
    extracted_value: Any = None
    unit: str = ""
    date_start: str = ""
    date_end: str = ""
    spatial_reference: str = ""
    confidence: str = "low"
    extraction_method: str = "structured_field"
    requires_manual_confirmation: bool = True
    approved: bool = False
    approved_by: str = ""
    approved_at: str = ""
    notes: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"
    pollutant: str = ""
    temporal_basis: str = ""
    measurement_role: str = "unknown"


def evidence_errors(item: SourceEvidenceRecord, *, quantitative: bool = False) -> list[str]:
    errors = []
    if item.evidence_type not in EVIDENCE_TYPES: errors.append("unknown_evidence_type")
    if not item.source_id: errors.append("source_identity_unresolved")
    if not item.file_reference or not item.row_reference or not item.provenance.get("checksum"):
        errors.append("traceable_provenance_required")
    if quantitative:
        try:
            if not math.isfinite(float(item.extracted_value)) or float(item.extracted_value) < 0: raise ValueError()
        except (ValueError, TypeError): errors.append("finite_nonnegative_value_required")
        if not validate_unit_compatibility(item.unit, item.unit)["compatible"]: errors.append("known_unit_required")
        try:
            if not item.date_start or not item.date_end or pd.Timestamp(item.date_end) < pd.Timestamp(item.date_start): raise ValueError()
        except (ValueError, TypeError): errors.append("explicit_period_required")
        if not item.temporal_basis: errors.append("temporal_basis_required")
    return errors


def review_evidence(item: SourceEvidenceRecord, action: str, *, actor: str, comment: str) -> SourceEvidenceRecord:
    if not actor.strip() or not comment.strip(): raise ValueError("Reviewer and comment required")
    if action not in {"confirm", "reject", "keep_unresolved"}: raise ValueError("Unknown review action")
    if action == "confirm":
        errors = evidence_errors(item, quantitative=item.evidence_type in ACTIVITY_UNITS or item.evidence_type in {"measured_concentration", "reported_pollutant_load"})
        if errors: raise ValueError(", ".join(errors))
    return replace(item, status={"confirm": "confirmed", "reject": "rejected", "keep_unresolved": "ambiguous"}[action], approved=action == "confirm", requires_manual_confirmation=action == "keep_unresolved", approved_by=actor, approved_at=datetime.now(timezone.utc).isoformat(), notes=comment)


def evidence_to_activity(item: SourceEvidenceRecord) -> ActivityRecord | None:
    if item.evidence_type not in ACTIVITY_UNITS: return None
    if item.status != "confirmed" or not item.approved or not item.approved_by or not item.approved_at: return None
    if evidence_errors(item, quantitative=True): return None
    if any(token in item.field_name.lower() for token in ("设计", "规模", "capacity")): return None
    if not validate_unit_compatibility(item.unit, ACTIVITY_UNITS[item.evidence_type])["compatible"]: return None
    value = float(convert_unit([item.extracted_value], item.unit, ACTIVITY_UNITS[item.evidence_type]).normalized_value.iloc[0])
    return ActivityRecord("activity_" + sha256(item.evidence_id.encode()).hexdigest()[:12], item.source_id, item.evidence_type, value, ACTIVITY_UNITS[item.evidence_type], item.date_start, item.date_end, item.temporal_basis, item.dataset_id or item.document_id, item.field_name, "observed", "reviewed", {**item.provenance, "evidence_id": item.evidence_id, "approved_by": item.approved_by})


def source_evidence_review_queue(records: list[SourceEvidenceRecord]) -> pd.DataFrame:
    return pd.DataFrame([{"evidence_id": e.evidence_id, "source": e.source_id or "unresolved", "proposed_activity": e.evidence_type, "value": e.extracted_value, "unit": e.unit, "source_document": e.file_reference, "context": e.provenance.get("context", e.field_name), "confidence": e.confidence, "reason": "; ".join(evidence_errors(e, quantitative=e.evidence_type in ACTIVITY_UNITS)), "recommended_action": "Confirm identity, unit and observation period; reject model-derived or unrelated records", "status": e.status} for e in records if e.status in {"candidate", "ambiguous"}])
