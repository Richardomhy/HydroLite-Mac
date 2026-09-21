"""Small business workbook and checksum-based refresh; imported facts await review."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json

import pandas as pd

from hydrolite.source_evidence import SourceEvidenceRecord
from hydrolite.source_evidence_scan import scan_source_evidence
from hydrolite.workspace import calculate_file_checksum

COMMON = ["source_id", "document_reference"]
SHEETS = {
    "排口基础信息": COMMON + ["source_name", "longitude", "latitude", "crs", "coordinate_reference"],
    "排放水量": COMMON + ["value", "unit", "flow_kind", "date_start", "date_end", "temporal_basis", "measurement_role"],
    "污染物监测": COMMON + ["pollutant", "value", "unit", "date_start", "date_end", "temporal_basis", "measurement_role", "qualifier"],
    "受纳水体": COMMON + ["receiving_water", "reach_id", "relation_evidence"],
    "污水处理设施": COMMON + ["evidence_type", "pollutant", "value", "unit", "flow_kind", "date_start", "date_end", "temporal_basis", "measurement_role", "reporting_authority", "load_scope"],
    "系数审批": ["factor_id", "proposed_action", "applicability_evidence", "reviewer", "comment"],
}


def write_completion_template(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        for name, fields in SHEETS.items(): pd.DataFrame(columns=fields).to_excel(writer, sheet_name=name, index=False)
    return path


def ingest_point_source_completion_template(path, sources):
    path = Path(path).resolve(); checksum = calculate_file_checksum(path)
    known = set(sources.source_id); records, issues, decisions = [], [], []
    with pd.ExcelFile(path) as book:
        for sheet, fields in SHEETS.items():
            if sheet not in book.sheet_names: issues.append({"sheet": sheet, "row": 0, "error": "sheet_missing"}); continue
            frame = book.parse(sheet).fillna("")
            if not set(fields) <= set(frame): issues.append({"sheet": sheet, "row": 1, "error": "columns_missing"}); continue
            for i, row in enumerate(frame.to_dict("records"), 2):
                if not any(str(v).strip() for v in row.values()): continue
                if sheet == "系数审批":
                    decisions.append({**row, "status": "proposal_only_requires_explicit_project_action", "checksum": checksum}); continue
                if row["source_id"] not in known or not row["document_reference"]:
                    issues.append({"sheet": sheet, "row": i, "error": "known_source_and_document_required"}); continue
                common = dict(source_id=row["source_id"], document_id=checksum[:16], file_reference=path.name, sheet_name=sheet, row_reference=str(i), provenance={"checksum": checksum, "document_reference": row["document_reference"], "identity_rule": "explicit_source_id", "context": row, "flow_kind": row.get("flow_kind", ""), "reporting_authority": row.get("reporting_authority", ""), "load_scope": row.get("load_scope", ""), "coordinate_reference": row.get("coordinate_reference", "")}, date_start=str(row.get("date_start", "")), date_end=str(row.get("date_end", "")), temporal_basis=str(row.get("temporal_basis", "")), measurement_role=str(row.get("measurement_role", "unknown")), unit=str(row.get("unit", "")), pollutant=str(row.get("pollutant", "")))
                items = []
                if sheet == "排口基础信息": items = [("location", "coordinates", json.dumps({"longitude": row["longitude"], "latitude": row["latitude"]}), str(row["crs"]))]
                elif sheet == "受纳水体": items = [(kind, field, row[field], "") for kind, field in (("receiving_water", "receiving_water"), ("outfall_to_reach_relation", "reach_id")) if row[field]]
                else:
                    kind = "discharge_flow" if sheet == "排放水量" else "measured_concentration" if sheet == "污染物监测" else row["evidence_type"]
                    if kind not in {"discharge_flow", "wastewater_volume", "measured_concentration", "treatment_capacity", "reported_pollutant_load", "treatment_efficiency"}:
                        issues.append({"sheet": sheet, "row": i, "error": "invalid_evidence_type"}); continue
                    value = row.get("value")
                    if row.get("qualifier"): value = str(row["qualifier"]) + str(value)
                    items = [(kind, str(row.get("flow_kind") or kind), value, "")]
                for kind, field, value, crs in items:
                    records.append(SourceEvidenceRecord("ev_" + sha256(f"{checksum}:{sheet}:{i}:{field}".encode()).hexdigest()[:16], evidence_type=kind, field_name=field, extracted_value=value, spatial_reference=crs, **common))
    return records, issues, decisions


def refresh_evidence(root, sources, existing, index=None, *, paths=None, template=False):
    """Discover names/stats only; parse changed files, retain all prior evidence revisions."""
    root = Path(root).expanduser().resolve(); index = dict(index or {})
    records = list(existing); audit, proposals = [], []
    if not root.is_dir():
        missing_ids = {eid for row in index.values() for eid in row.get("evidence_ids", [])}
        records = [replace(e, status="external_evidence_missing", approved=False) if e.evidence_id in missing_ids else e for e in records]
        for row in index.values(): row["status"] = "external_evidence_missing"
        return records, index, [{"status": "external_evidence_missing", "file_reference": "."}], proposals
    if paths is None:
        supported = {".xlsx", ".xls", ".csv", ".docx", ".txt", ".json", ".gpkg", ".shp", ".geojson"}
        paths = [p for p in root.rglob("*") if p.is_file() and not p.is_symlink() and p.suffix.lower() in supported and (p.suffix.lower() in {".xlsx", ".xls", ".docx", ".gpkg", ".shp", ".geojson"} or any(k in p.name.lower() for k in ("排口", "排水", "废水", "污水", "流量", "水量", "受纳", "outfall", "effluent"))) and not any(t in p.parts for t in ("external", "TxtInOut", "data_demo", "templates", "templates_export", ".git", "output", "__pycache__"))]
    present = set()
    for path in sorted(paths):
        path = Path(path)
        if path.is_symlink(): continue
        logical = path.resolve().relative_to(root).as_posix(); present.add(logical)
        old = index.get(logical, {})
        if not path.is_file(): audit.append({"file_reference": logical, "status": "external_evidence_missing"}); continue
        stat = path.stat()
        if stat.st_size > 30_000_000: audit.append({"file_reference": logical, "status": "manual_review_size_limit"}); continue
        # Hash selected evidence inputs, never reparse unchanged content.
        checksum = calculate_file_checksum(path)
        if old.get("checksum") == checksum and old.get("status") != "external_evidence_missing":
            audit.append({"file_reference": logical, "status": "unchanged_skip"}); continue
        if template:
            added, errors, decisions = ingest_point_source_completion_template(path, sources)
            if errors: audit.extend({"file_reference": logical, "status": "import_error", **e} for e in errors); continue
            proposals.extend(decisions)
        else:
            added, scanned = scan_source_evidence(root, sources, paths=[path])
            if len(scanned) and scanned.iloc[0].status != "searched": audit.extend(scanned.to_dict("records")); continue
            if path.suffix.lower() in {".gpkg", ".shp", ".geojson"}:
                import geopandas as gpd
                import pyogrio
                from hydrolite.point_source_spatial import coordinate_evidence_from_layer
                layers = [name for name, _ in pyogrio.list_layers(path)] if path.suffix.lower() == ".gpkg" else [None]
                for layer in layers:
                    added.extend(coordinate_evidence_from_layer(gpd.read_file(path, layer=layer), sources, reference=logical + (":" + layer if layer else ""), checksum=checksum))
        previous_ids = set(old.get("evidence_ids", []))
        records = [replace(e, status="superseded", approved=False, notes=e.notes + "; newer source revision retained") if e.evidence_id in previous_ids else e for e in records]
        added_by_id = {e.evidence_id: e for e in added}
        records = [added_by_id[e.evidence_id] if e.evidence_id in added_by_id and e.evidence_id in previous_ids else e for e in records]
        seen = {e.evidence_id for e in records}
        records.extend(e for e in added if e.evidence_id not in seen)
        index[logical] = {"checksum": checksum, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "evidence_ids": [e.evidence_id for e in added], "status": "parsed"}
        audit.append({"file_reference": logical, "status": "parsed", "evidence_count": len(added)})
    for logical, old in index.items():
        if (root / logical).is_file(): continue
        old["status"] = "external_evidence_missing"
        audit.append({"file_reference": logical, "status": "external_evidence_missing"})
        records = [replace(e, status="external_evidence_missing", approved=False) if e.evidence_id in old.get("evidence_ids", []) else e for e in records]
    return records, index, audit, proposals


def consolidated_requests(source_count):
    businesses = [
        ("DR01", "排口基础信息表", "排口基础信息", "确认身份与坐标来源"),
        ("DR02", "排口实际排放水量表", "排放水量", "实测或报送实际水量；设计规模不能替代"),
        ("DR03", "排口污染物监测表", "污染物监测", "同源同时段出水浓度；COD 不等于 CODMn"),
        ("DR04", "排口与受纳水体对应表", "受纳水体", "正式河段编号及空间一致性"),
        ("DR05", "污水处理设施运行表", "污水处理设施", "实际运行、进出水与排放语义"),
        ("DR06", "项目系数适用性审批表", "系数审批", "仅需系数的源，逐项审批，不自动批准"),
    ]
    return pd.DataFrame([{"request_id": rid, "business_name": name, "priority": "P0", "why_needed": why, "affected_sources": source_count, "required_fields": ";".join(SHEETS[sheet]), "units": "m3/s or m3/day; mg/L; explicit CRS; kg/day", "time_requirement": "same source and matching observation period", "acceptable_format": "provided XLSX sheet", "acceptable_alternative": "dated monitoring/operation record with source ID and original document reference", "calculation_blocked": "point-source load / formal reach attribution", "current_evidence": "See per-source closure; request only missing fields", "example": "source_id=anonymous_01; date_start=<ISO date>; value=<observed>; document_reference=<record>"} for rid, name, sheet, why in businesses])
