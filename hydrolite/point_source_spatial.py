"""Coordinate evidence precedes spatial confidence; candidates are not approvals."""

import json
import math
from hashlib import sha256
from datetime import datetime, timezone

import pandas as pd
from pyproj import CRS

from hydrolite.source_reach_mapping import map_source_reaches, normalize_waterbody_name
from hydrolite.source_evidence import SourceEvidenceRecord

MAPPING_RULES = {
    "high": "confirmed CRS + explicit/name evidence + unique basin + distance consistency",
    "medium": "confirmed CRS + reviewed relation + basin consistency + distance consistency",
    "low": "nearest geometry only; not eligible",
    "unresolved": "missing CRS or computational reach crosswalk",
    "conflicting": "documented receiving relation disagrees with spatial evidence",
}


def coordinate_evidence_from_layer(frame, sources, *, reference, checksum):
    """Only named/ID-matched point geometry from a declared layer CRS is evidence."""
    if frame.crs is None: return []
    result = []
    for idx, row in frame.iterrows():
        point = row.geometry
        if point is None or point.geom_type != "Point" or not point.is_valid: continue
        matches = set()
        for column in ("source_id", "排口名称", "排污口名称", "name"):
            value = row.get(column)
            if value is not None:
                matches.update(sources.loc[sources.source_id.eq(str(value)) | sources.name.eq(str(value)), "source_id"])
        if len(matches) != 1: continue
        source_id = next(iter(matches))
        result.append(SourceEvidenceRecord("ev_geo_" + sha256(f"{checksum}:{reference}:{idx}".encode()).hexdigest()[:16], source_id, "location", file_reference=reference, row_reference=str(idx), field_name="geometry", extracted_value=json.dumps({"longitude": point.x, "latitude": point.y}), spatial_reference=str(frame.crs), extraction_method="confirmed_by_metadata", status="confirmed", approved=True, approved_by="rule:geometry_with_explicit_layer_crs", approved_at=datetime.now(timezone.utc).isoformat(), confidence="high", requires_manual_confirmation=False, provenance={"checksum": checksum, "crs_source": "gis_layer", "geometry_is_coordinate_source": True, "coordinate_reference": reference, "identity_rule": "exact_unique_source_id_or_name"}))
    return result


def coordinate_audit(sources, evidence):
    rows = []
    for s in sources.to_dict("records"):
        candidates = [e for e in evidence if e.source_id == s["source_id"] and e.evidence_type == "location" and e.status not in {"superseded", "rejected", "external_evidence_missing"}]
        trusted = [e for e in candidates if e.spatial_reference and e.status == "confirmed" and e.approved and e.approved_by and e.approved_at and e.provenance.get("checksum") and ((e.provenance.get("geometry_is_coordinate_source") and e.provenance.get("crs_source") in {"file_metadata", "gis_layer"}) or e.provenance.get("coordinate_reference"))]
        status, crs, origin = "requires_manual_confirmation", "", "numeric_range_is_not_CRS_evidence"
        try:
            x, y = float(s["longitude"]), float(s["latitude"])
            if not math.isfinite(x) or not math.isfinite(y): raise ValueError()
        except (ValueError, TypeError): x, y, status = None, None, "unknown"
        systems = set()
        for e in trusted:
            try: systems.add(CRS.from_user_input(e.spatial_reference).to_string())
            except (ValueError, TypeError): status = "conflicting"
        if len(systems) > 1: status = "conflicting"
        elif len(systems) == 1 and x is not None and status != "conflicting":
            crs = next(iter(systems)); status = "confirmed"; origin = ";".join(e.evidence_id for e in trusted)
        positions = set()
        for e in trusted:
            try:
                value = json.loads(e.extracted_value)
                positions.add((float(value["longitude"]), float(value["latitude"])))
            except (ValueError, TypeError, KeyError): pass
        if len(positions) > 1: status = "conflicting"
        rows.append({"source_id": s["source_id"], "name": s["name"], "raw_x": x, "raw_y": y, "coordinate_status": status, "proposed_crs": crs or ("EPSG:4326 (unconfirmed)" if x is not None and -180 <= x <= 180 and -90 <= y <= 90 else "unknown"), "coordinate_crs": crs, "evidence": origin, "confidence": "high" if status == "confirmed" else "low", "conflict": status == "conflicting", "recommended_action": "Verify original coordinate source and datum; do not approve by value range"})
    return pd.DataFrame(rows)


def point_source_mapping(sources, evidence, basins, reaches, *, aliases=None, near_distance_m=100):
    near_distance_m = float(near_distance_m)
    if not math.isfinite(near_distance_m) or near_distance_m <= 0:
        raise ValueError("near_distance_m must be finite and positive")
    coordinates = coordinate_audit(sources, evidence)
    rows = []
    for s in sources.to_dict("records"):
        coord = coordinates.loc[coordinates.source_id.eq(s["source_id"])].iloc[0]
        records = [e for e in evidence if e.source_id == s["source_id"] and e.status == "confirmed" and e.approved and e.approved_by and e.approved_at]
        names = {str(e.extracted_value) for e in records if e.evidence_type == "receiving_water"}
        ids = {str(e.extracted_value) for e in records if e.evidence_type == "outfall_to_reach_relation"}
        s.update(receiving_water=next(iter(names)) if len(names) == 1 else "", explicit_reach_id=next(iter(ids)) if len(ids) == 1 else "", explicit_relation_evidence=bool(ids))
        assumed = coord.coordinate_crs or ("EPSG:4326" if str(coord.proposed_crs).startswith("EPSG:4326") else None)
        mapped = map_source_reaches(pd.DataFrame([s]), basins, reaches, source_crs=assumed, coordinate_evidence=coord.evidence if coord.coordinate_status == "confirmed" else "", analysis_crs=basins.crs, aliases=aliases, near_distance_m=near_distance_m).iloc[0].to_dict()
        mapped["candidate_reach_id"] = mapped["reach_id"]
        mapped["reach_subbasin"] = "unknown"
        if mapped["reach_id"] and "reach_id" in reaches and "subbasin_id" in reaches:
            matches = reaches[reaches.reach_id.eq(mapped["reach_id"])]
            if len(matches) == 1: mapped["reach_subbasin"] = str(matches.iloc[0].subbasin_id)
        consistent = mapped["distance_m"] is not None and mapped["distance_m"] <= near_distance_m
        conflict = len(names) > 1 or len(ids) > 1
        if names or ids:
            conflict |= not consistent or mapped["mapping_method"] not in {"explicit", "receiving_water"}
        if mapped["reach_subbasin"] != "unknown" and mapped["subbasin_id"] != mapped["reach_subbasin"]: conflict = True
        if conflict: mapped["confidence"] = "conflicting"
        elif coord.coordinate_status != "confirmed" or not mapped["candidate_reach_id"]: mapped["confidence"] = "unresolved"
        if mapped["mapping_method"] == "nearest_reach": mapped["mapping_method"] = "nearest_reach_fallback"
        mapped["spatial_consistency"] = consistent and not conflict
        mapped["reach_confirmed"] = mapped["confidence"] in {"high", "medium"} and mapped["spatial_consistency"]
        if not mapped["reach_confirmed"]: mapped["reach_id"] = None
        mapped["manual_confirmation"] = mapped["confidence"] != "high"
        mapped["reason"] = "CRS, name/distance consistency and formal reach crosswalk must all be evidenced"
        rows.append(mapped)
    return coordinates, pd.DataFrame(rows)
