"""M9A.2 coordination over existing inventory, approvals and project versioning."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
import json

import pandas as pd

from hydrolite.emission_factor_approval import EmissionFactorApproval, approved_project_factors, build_project_factor_set
from hydrolite.point_source_completion import refresh_evidence, consolidated_requests, write_completion_template
from hydrolite.point_source_evidence import audit_source_identity, factor_decision_records
from hydrolite.point_source_load import point_source_loads
from hydrolite.point_source_readiness import point_source_readiness, DEFAULT_THRESHOLDS
from hydrolite.point_source_spatial import point_source_mapping, MAPPING_RULES
from hydrolite.source_evidence import SourceEvidenceRecord
from hydrolite.source_evidence_workflow import checked_output, read_evidence_state, _save_state
from hydrolite.source_load_ledger import validate_source_load_ledger
from hydrolite.water_environment import ROOT, DEFAULT_WORKSPACE, _xlsx, _json
from hydrolite.water_environment_contracts import EmissionFactor, POLLUTANTS

DEFAULT_OUTPUT = ROOT / "output/water_environment/m9a2"
COMMANDS = {"point-source-status", "point-source-map", "point-source-load", "data-request", "evidence-refresh"}


def point_output(path):
    root = checked_output(path)
    old = (ROOT / "output/water_environment/m9a1").resolve()
    if root == old or old in root.parents or root in old.parents: raise ValueError("M9A.1 frozen baseline is protected")
    if root.exists() and any(p.is_symlink() for p in root.rglob("*")): raise ValueError("Output symlinks prohibited")
    return root


def run_point_source_closure(*, output_dir=DEFAULT_OUTPUT, workspace_dir=DEFAULT_WORKSPACE, source_root=None, template=None, refresh=False, finalize=False):
    import geopandas as gpd
    import yaml
    root = point_output(output_dir); workspace = Path(workspace_dir).expanduser().resolve()
    parent = ROOT / "output/water_environment/m9a1"
    parent_facts = json.loads((parent / "reports/m9a1_manifest.json").read_text())
    manifest_path = root / "reports/m9a2_manifest.json"
    if manifest_path.is_file():
        prior = json.loads(manifest_path.read_text())
        if prior.get("project_version"):
            if refresh or template: raise ValueError("Frozen Version 5: use a new output directory for revisions")
            return prior
    state = read_evidence_state(root) or (read_evidence_state(DEFAULT_OUTPUT) if root != DEFAULT_OUTPUT.resolve() else {}) or json.loads((parent / "review_state.json").read_text())
    sources = pd.read_excel(ROOT / "output/water_environment/m9a/inventory/pollution_source_inventory.xlsx")
    sources = sources[sources.source_type.isin(["direct_outfall", "wastewater_treatment"]) & sources.status.isin(["accepted", "manual_confirmation_required"])].copy()
    evidence = [SourceEvidenceRecord(**e) for e in state["evidence"]]
    if "file_index" not in state:
        state["file_index"] = {r["file_reference"]: {"checksum": r.get("checksum"), "evidence_ids": [e.evidence_id for e in evidence if e.file_reference == r["file_reference"]], "status": "parsed"} for r in state.get("scan", []) if r["status"] == "searched"}
    audit = []
    if refresh and source_root:
        original = Path(source_root).expanduser().resolve()
        if original == root or original in root.parents or root in original.parents: raise ValueError("Source and outputs must be separate")
        evidence, state["file_index"], audit, _ = refresh_evidence(original, sources, evidence, state["file_index"])
    if template:
        template_path = Path(template).expanduser().resolve()
        evidence, state["template_index"], imported, proposals = refresh_evidence(template_path.parent, sources, evidence, state.get("template_index"), paths=[template_path], template=True)
        audit.extend(imported); state.setdefault("factor_proposals", []).extend(proposals)
    state["evidence"] = [e.as_dict() for e in evidence]
    state["incremental_audit"] = audit or state.get("incremental_audit", [])
    identity = audit_source_identity(sources)
    # Reviewed coordinate corrections preserve original inventory and source evidence.
    for e in evidence:
        if e.evidence_type == "location" and e.status == "confirmed" and e.approved and e.approved_by and e.provenance.get("coordinate_reference"):
            try:
                values = json.loads(e.extracted_value)
                sources.loc[sources.source_id.eq(e.source_id), ["longitude", "latitude"]] = [float(values["longitude"]), float(values["latitude"])]
            except (ValueError, TypeError, KeyError): pass
    basins = gpd.read_file(workspace / "derived/m8b/reviewed_subbasins.geojson")
    reaches = gpd.read_file(workspace / "derived/m8b/reviewed_river_lines.geojson")
    if "名称|name" in reaches: reaches = reaches.rename(columns={"名称|name": "name"})
    cfg = workspace / "configs/m9a2/point_source.yaml"
    config = yaml.safe_load(cfg.read_text()) if cfg.is_file() else {}
    config = config or {}
    crosswalk = workspace / "configs/m9a1/reach_crosswalk.csv"
    if crosswalk.is_file():
        table = pd.read_csv(crosswalk)
        if not {"name", "reach_id", "evidence", "approved"} <= set(table): raise ValueError("Reach crosswalk requires explicit evidence and approval")
        table = table[table.approved.eq(True) & table.evidence.notna()]
        valid = set(pd.read_csv(workspace / "standardized/m8b/reaches.csv").id)
        if table.name.duplicated().any() or not set(table.reach_id) <= valid: raise ValueError("Invalid formal reach crosswalk")
        reaches = reaches.merge(table[["name", "reach_id"]], on="name", how="left")
    coordinates, mapping = point_source_mapping(sources, evidence, basins, reaches, aliases=config.get("waterbody_aliases"), near_distance_m=config.get("thresholds", {}).get("near_distance_m", 100))
    factors = [EmissionFactor(**f) for f in state["factors"]]
    approvals = [EmissionFactorApproval(**a) for a in state["approvals"]]
    approved = approved_project_factors(factors, approvals, state["project_id"])
    ledger, flow, concentration, alignment, reported, comparison = point_source_loads(sources, identity, evidence, approved)
    decisions = factor_decision_records(factors, approvals, state["project_id"])
    factor_set = build_project_factor_set(state["project_id"], factors, approvals, [str(r.factor_id) for r in decisions.itertuples() if r.reviewer_action_required])
    closure, coverage, gates = point_source_readiness(sources, identity, coordinates, mapping, flow, concentration, alignment, ledger, approved, thresholds=config.get("thresholds"), hydrology_gate=parent_facts["hydrology_gate"])
    check = validate_source_load_ledger(ledger)
    if check["status"] != "passed": raise ValueError("Source ledger consistency failed")
    paths = {}
    def write(key, filename, sheets):
        frames = {}
        for name, data in sheets.items():
            frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
            if frame.empty and not len(frame.columns): frame = pd.DataFrame([{"status": "no_usable_evidence", "count": 0}])
            for col in frame.select_dtypes(include="object"):
                frame[col] = frame[col].map(lambda v: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "@")) else v)
            frames[name] = frame
        paths[key] = _xlsx(root / filename, frames)
    write("identity", "identity/point_source_identity_audit.xlsx", {"identity": identity})
    write("coordinates", "spatial/coordinate_review_queue.xlsx", {"coordinates": coordinates})
    write("mapping", "spatial/source_reach_candidates.xlsx", {"candidates": mapping, "rules": [{"confidence": k, "rule": v} for k, v in MAPPING_RULES.items()]})
    write("mapping_review", "spatial/source_reach_review_queue.xlsx", {"review": mapping[mapping.confidence.ne("high")]})
    paths["geojson"] = root / "spatial/source_mapping.geojson"
    features = []
    for row in mapping.to_dict("records"):
        source = sources.loc[sources.source_id.eq(row["source_id"])].iloc[0]
        crs = coordinates.loc[coordinates.source_id.eq(row["source_id"]), "coordinate_crs"].iloc[0]
        geometry = None
        if crs:
            from shapely.geometry import Point, mapping as geometry_mapping
            geometry = geometry_mapping(gpd.GeoSeries([Point(source.longitude, source.latitude)], crs=crs).to_crs(4326).iloc[0])
        features.append({"type": "Feature", "geometry": geometry, "properties": {"source_id": row["source_id"], "reach_id": row["reach_id"], "candidate_river_line": row["candidate_river_line"], "confidence": row["confidence"], "note": "Geometry withheld until coordinate CRS confirmed" if geometry is None else "CRS confirmed"}})
    _json(paths["geojson"], {"type": "FeatureCollection", "features": features})
    write("flow", "flow/source_flow_evidence.xlsx", {"evidence": flow, "status": [{"sources_searched": len(sources), "linked_flow_records": int(flow.source_id.isin(set(sources.source_id)).sum())}], "incremental_scan": state["incremental_audit"]})
    write("alignment", "flow/flow_concentration_alignment.xlsx", {"alignment": alignment, "status": [{"pairs": len(alignment), "rule": "same source; actual flow; effluent; exact/same_day"}]})
    write("concentration", "concentration/source_concentration_audit.xlsx", {"audit": concentration})
    write("comparison", "load/measured_reported_load_comparison.xlsx", {"comparison": comparison, "reported": reported, "measured": alignment[alignment.status.eq("measured")]})
    write("ledger", "load/point_source_load_ledger_v3.xlsx", {"ledger": ledger, "validation": [check]})
    write("decisions", "factors/factor_decision_pack.xlsx", {"decisions": decisions, "grouped_decisions": decisions.groupby(["source_category", "pollutant"]).size().reset_index(name="candidate_count"), "imported_proposals": state.get("factor_proposals", [])})
    requests = consolidated_requests(len(sources))
    write("requests", "requests/m9a2_project_data_request_pack.xlsx", {"requests": requests})
    paths["template"] = write_completion_template(root / "requests/m9a2_point_source_data_template.xlsx")
    write("closure", "readiness/point_source_readiness.xlsx", {"sources": closure, "coverage": [{"metric": k, "value": v} for k, v in coverage.items()]})
    write("gates", "readiness/m9b_gate_summary.xlsx", {"gates": [{"gate": k, "value": json.dumps(v, ensure_ascii=False)} for k, v in gates.items()]})
    count = lambda frame, column: frame[column].value_counts().to_dict()
    facts = {"project_id": state["project_id"], "parent_version": parent_facts["project_version"], "ledger_version": 3, "factor_set": parent_facts["factor_set"], "source_count": len(sources), "identity": count(identity, "identity_status"), "coordinates": count(coordinates, "coordinate_status"), "mapping_methods": count(mapping, "mapping_method"), "mapping_confidence": count(mapping, "confidence"), "spatial": {"subbasin_mapped": int(mapping.subbasin_id.notna().sum()), "river_line_candidates": int(mapping.candidate_river_line.notna().sum()), "formal_reach_candidates": int(mapping.candidate_reach_id.notna().sum()), "reach_confirmed": int(mapping.reach_confirmed.sum())}, "flow": count(flow, "kind"), "concentration_context": count(concentration[concentration.source_id.isin(set(sources.source_id))], "context"), "concentration_records": len(concentration[concentration.source_id.isin(set(sources.source_id))]), "concentration_temporal_range": [str(concentration.date_start.min()), str(concentration.date_end.max())], "factor_decisions": count(decisions, "recommended_decision"), "approved_factors": len(approved), "decision_records": len(decisions), "load_comparison": count(comparison, "status"), "ledger": [{"pollutant": p, "quantified": int((ledger.pollutant.eq(p) & ledger.net_emission_load.notna()).sum()), "unquantified": int((ledger.pollutant.eq(p) & ledger.net_emission_load.isna()).sum()), "measured": int((ledger.pollutant.eq(p) & ledger.calculation_status.eq("measured")).sum()), "reported": int((ledger.pollutant.eq(p) & ledger.calculation_status.eq("reported")).sum())} for p in POLLUTANTS], "ledger_check": check, "coverage": coverage, "gates": gates, "requests": {"old_P0": 33, "consolidated": len(requests), "P0": int(requests.priority.eq("P0").sum())}, "incremental_scan": state["incremental_audit"], "limitations": ["Source-only evidence; no pollutant transport or river input", "No project factor decisions impersonated", "Unknown CRS is not approved from coordinate range", "No diffuse-source development; water_quality remains planned", "Point-source eligibility is not basin readiness"], "timestamp": datetime.now(timezone.utc).isoformat()}
    linked_flow = flow[flow.source_id.isin(set(sources.source_id))]
    facts["unlinked_flow_candidates"] = len(flow) - len(linked_flow)
    facts["flow"] = count(linked_flow, "kind")
    facts["flow_sources_missing"] = len(sources) - linked_flow.source_id.nunique()
    dated = concentration[concentration.source_id.isin(set(sources.source_id)) & concentration.date_start.ne("") & concentration.date_end.ne("")]
    facts["concentration_temporal_range"] = [str(dated.date_start.min()), str(dated.date_end.max())] if len(dated) else []
    facts["factor_approval_status"] = {"reviewed_candidates": len(decisions), "project_approved": len(approved), "pending_decision": int(decisions.reviewer_action_required.sum()), "CODMn": "missing", "semantics": "generation only; no COD conversion"}
    headings = ["Baseline / 点源基线", "Identity / 身份", "CRS / 坐标基准", "Reach / 河段", "Flow / 水量", "Concentration / 浓度", "Load / 负荷", "Factors / 系数决策", "Coverage / 覆盖", "Requests / 补资料", "Point eligibility / 点源资格", "Overall gate / 总体门禁", "Blockers / 剩余阻断"]
    sections = [{"source_count": len(sources), "parent": facts["parent_version"]}, facts["identity"], facts["coordinates"], facts["spatial"], facts["flow"], facts["concentration_context"], facts["ledger"], facts["factor_decisions"], coverage, requests.to_dict("records"), gates["point_source_m9b_eligibility"], gates["pollutant_delivery_model_gate"], gates["blockers"]]
    for language in ("zh", "en"):
        path = root / f"reports/m9a2_point_source_closure_report_{language}.md"; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# M9A.2 Point Source Evidence Closure / 点源证据闭环\n\n" + "\n\n".join(f"## {n}. {h}\n\n```json\n{json.dumps(v, ensure_ascii=False, indent=2)}\n```" for n, (h, v) in enumerate(zip(headings, sections), 1)) + "\n\nReal-data diagnostic only; technical review is not independent scientific approval.\n\n已停止，没有开始 M9B。\n", encoding="utf-8")
        paths["report_" + language] = path
    state["outputs_stale"] = False
    state["point_source_config"] = {"thresholds": gates["thresholds"], "mapping_rules": MAPPING_RULES, "waterbody_aliases": config.get("waterbody_aliases", {})}
    state["project_factor_set"] = factor_set.as_dict()
    facts["factor_set"] = factor_set.factor_set_id
    _save_state(root, state)
    facts["snapshot_content_hash"] = sha256(json.dumps({"evidence": state["evidence"], "closure": closure.to_dict("records"), "decisions": decisions.to_dict("records"), "gates": gates}, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    facts["outputs"] = {k: str(p.relative_to(root)) for k, p in paths.items()}
    paths["manifest"] = _json(manifest_path, facts)
    if finalize:
        from hydrolite.source_evidence_delivery import finalize_evidence_delivery
        facts.update(finalize_evidence_delivery(workspace, root, paths, facts, parent_version=parent_facts["project_version"], version_number=5, phase="m9a2", stage="point_source_evidence_closure"))
    return facts
