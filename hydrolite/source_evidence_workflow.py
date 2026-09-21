"""M9A.1 evidence closure, using the existing inventory and immutable M9A ledger."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import uuid

import pandas as pd
import yaml

from hydrolite.emission_factor_approval import EmissionFactorApproval, approve_factor, approved_project_factors, build_project_factor_set, factor_stage
from hydrolite.emission_factor_registry import load_emission_factors
from hydrolite.provenance import is_protected_path
from hydrolite.source_evidence import SourceEvidenceRecord, review_evidence, source_evidence_review_queue
from hydrolite.source_evidence_ledger import build_evidence_ledger
from hydrolite.source_evidence_readiness import CATEGORIES, build_data_requests, evaluate_evidence_readiness
from hydrolite.source_evidence_scan import scan_source_evidence
from hydrolite.source_reach_mapping import map_source_reaches
from hydrolite.water_environment import ROOT, DEFAULT_WORKSPACE, PROJECT_ID, _xlsx, _json
from hydrolite.water_environment_contracts import POLLUTANTS

DEFAULT_OUTPUT = ROOT / "output/water_environment/m9a1"
COMMANDS = {"evidence", "evidence-review", "factor-candidates", "factor-set", "spatial-map", "readiness"}


def checked_output(output_dir):
    path = Path(output_dir).expanduser().resolve()
    old = (ROOT / "output/water_environment/m9a").resolve()
    if is_protected_path(path) or path == old or old in path.parents or path in old.parents:
        raise ValueError("Protected path or M9A baseline cannot be used for output")
    return path


def _save_state(root, state):
    root = checked_output(root); root.mkdir(parents=True, exist_ok=True)
    target = root / "review_state.json"
    if target.is_symlink(): raise ValueError("Review state must not be a symlink")
    temporary = root / (".review_" + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temporary, target)
    finally: temporary.unlink(missing_ok=True)


def read_evidence_state(root=DEFAULT_OUTPUT):
    path = checked_output(root) / "review_state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def record_review(root, object_id, action, *, actor, comment, factor=False, corrections=None):
    from hydrolite.runtime_db import create_audit_event_record
    for name in ("m9a1_manifest.json", "m9a2_manifest.json"):
        frozen = checked_output(root) / "reports" / name
        if frozen.is_file() and json.loads(frozen.read_text(encoding="utf-8")).get("project_version"):
            raise ValueError("Frozen output is immutable; use a new output directory for revised evidence")
    state = read_evidence_state(root)
    if not state: raise ValueError("Run evidence search before review")
    if factor:
        from hydrolite.water_environment_contracts import EmissionFactor
        matches = [r for r in state["factors"] if r["factor_id"] == object_id]
        if len(matches) != 1: raise ValueError("Unknown or ambiguous factor ID")
        item = EmissionFactor(**matches[0])
        decision = approve_factor(item, state["project_id"], action, actor=actor, comment=comment)
        state["approvals"].append(decision.as_dict())
    else:
        matches = [i for i, r in enumerate(state["evidence"]) if r["evidence_id"] == object_id]
        if len(matches) != 1: raise ValueError("Unknown or ambiguous evidence ID")
        index = matches[0]
        item = SourceEvidenceRecord(**state["evidence"][index])
        if corrections:
            allowed = {"source_id", "unit", "date_start", "date_end", "temporal_basis", "measurement_role"}
            if set(corrections) - allowed: raise ValueError("Unsupported evidence correction")
            valid_sources = set(pd.read_excel(ROOT / "output/water_environment/m9a/inventory/pollution_source_inventory.xlsx").source_id)
            if corrections.get("source_id", item.source_id) not in valid_sources: raise ValueError("Unknown source ID")
            item = replace(item, **corrections, provenance={**item.provenance, "original_evidence": item.as_dict(), "review_corrections": corrections})
        item = review_evidence(item, action, actor=actor, comment=comment)
        state["evidence"][index] = item.as_dict()
    event = {"event_id": "evt_" + uuid.uuid4().hex[:12], "timestamp": datetime.now(timezone.utc).isoformat(), "project_id": state["project_id"], "actor": actor, "action": action, "object_type": "emission_factor" if factor else "source_evidence", "object_id": object_id, "summary": comment, "metadata": {"review_workflow": "m9a1", "requires_rebuild": True}}
    create_audit_event_record(**event)
    state.setdefault("audit", []).append(event)
    state["outputs_stale"] = True
    _save_state(root, state)
    return {"status": "review_recorded", "outputs_stale": True, "message": "Re-run readiness to rebuild; frozen project version remains unchanged."}


def run_evidence_closure(source_root=None, *, workspace_dir=DEFAULT_WORKSPACE, output_dir=DEFAULT_OUTPUT, finalize=False):
    import geopandas as gpd
    from hydrolite.water_environment_contracts import EmissionFactor
    from hydrolite.source_load_ledger import validate_source_load_ledger
    root = checked_output(output_dir); workspace = Path(workspace_dir).expanduser().resolve()
    if root.exists() and any(p.is_symlink() for p in root.rglob("*")): raise ValueError("Output tree must not contain symlinks")
    if source_root is not None:
        source_path = Path(source_root).expanduser().resolve()
        if not source_path.is_dir(): raise FileNotFoundError(f"external_project_storage_unavailable: {source_path}")
        if root == source_path or root in source_path.parents or source_path in root.parents: raise ValueError("Outputs must be separate from source data")
    m9a = ROOT / "output/water_environment/m9a"
    sources = pd.read_excel(m9a / "inventory/pollution_source_inventory.xlsx", sheet_name="inventory")
    sources = sources[sources.status.isin(["accepted", "manual_confirmation_required"])].copy()
    state = read_evidence_state(root)
    frozen_manifest = root / "reports/m9a1_manifest.json"
    if frozen_manifest.is_file():
        frozen = json.loads(frozen_manifest.read_text(encoding="utf-8"))
        if frozen.get("project_version"):
            if state.get("outputs_stale"): raise ValueError("Frozen output is immutable; use a new output directory for revised evidence")
            return {"status": "passed", "manifest": str(frozen_manifest), "pollutant_delivery_model_gate": frozen["gates"]["pollutant_delivery_model_gate"], "facts": frozen}
    if not state:
        if source_root is None: return {"status": "output_missing", "message": "Use evidence --source-root <external project> first"}
        records, scan = scan_source_evidence(source_path, sources)
        # Exact source identity + explicit date/unit supports extraction confirmation, not regulatory validity.
        accepted_ids = set(sources.loc[sources.status.eq("accepted"), "source_id"])
        for i, item in enumerate(records):
            if item.source_id in accepted_ids and item.evidence_type == "measured_concentration" and item.date_start and item.unit and isinstance(item.extracted_value, float):
                try:
                    item = review_evidence(replace(item, measurement_role="outfall"), "confirm", actor="rule:exact_dated_outfall_concentration", comment="Confirmed structured extraction only; instantaneous sample is not continuous emission evidence")
                    records[i] = replace(item, extraction_method="confirmed_by_rule")
                except ValueError: pass
        factors = load_emission_factors(ROOT / "config/water_environment/emission_factors.example.yaml")
        state = {"project_id": PROJECT_ID, "evidence": [e.as_dict() for e in records], "scan": json.loads(scan.to_json(orient="records", force_ascii=False)), "factors": [f.as_dict() for f in factors], "approvals": [], "outputs_stale": True, "spatial": {"source_crs": "EPSG:4326", "coordinate_evidence": "", "note": "M9A longitude/latitude CRS assumption is not an approved coordinate source"}}
        _save_state(root, state)
    from hydrolite.emission_factor_approval import load_verified_candidates
    candidates, references = load_verified_candidates(ROOT / "config/water_environment/factor_sources.yaml")
    ids = {f["factor_id"] for f in state["factors"]}
    state["factors"].extend(f.as_dict() for f in candidates if f.factor_id not in ids)
    state["factor_sources"] = references
    records = [SourceEvidenceRecord(**row) for row in state["evidence"]]
    factors = [EmissionFactor(**row) for row in state["factors"]]
    approvals = [EmissionFactorApproval(**row) for row in state["approvals"]]
    approved = approved_project_factors(factors, approvals, PROJECT_ID)
    for kind, column in (("receiving_water", "receiving_water"), ("outfall_to_reach_relation", "explicit_reach_id")):
        values = {e.source_id: e.extracted_value for e in records if e.evidence_type == kind and e.status == "confirmed" and e.approved}
        sources[column] = sources.source_id.map(values).fillna("")
    sources["explicit_relation_evidence"] = sources.explicit_reach_id.ne("")
    basins = gpd.read_file(workspace / "derived/m8b/reviewed_subbasins.geojson")
    reaches = gpd.read_file(workspace / "derived/m8b/reviewed_river_lines.geojson")
    if "名称|name" in reaches: reaches = reaches.rename(columns={"名称|name": "name"})
    # A reviewed crosswalk is optional; never invent IDs for surveyed lines or assign all to R_OUTLET.
    crosswalk = workspace / "configs/m9a1/reach_crosswalk.csv"
    if crosswalk.is_file():
        links = pd.read_csv(crosswalk)
        if not {"name", "reach_id", "evidence", "approved"} <= set(links): raise ValueError("Crosswalk evidence/approval required")
        links = links[links.approved.eq(True) & links.evidence.notna()]
        if links.name.duplicated().any(): raise ValueError("Ambiguous reach crosswalk")
        valid_ids = set(pd.read_csv(workspace / "standardized/m8b/reaches.csv").id)
        if not set(links.reach_id) <= valid_ids: raise ValueError("Crosswalk references unknown M8B reaches")
        reaches = reaches.merge(links[["name", "reach_id"]], on="name", how="left")
    mapping = map_source_reaches(sources, basins, reaches, source_crs=state["spatial"].get("source_crs"), coordinate_evidence=state["spatial"].get("coordinate_evidence", ""), analysis_crs=basins.crs)
    ledger, activities = build_evidence_ledger(sources, records, approved)
    hydrology = json.loads((ROOT / "output/real_project_validation/m8b/reports/m8b_manifest.json").read_text())
    gates, activity_gap, categories = evaluate_evidence_readiness(sources, records, activities, approved, mapping, ledger, hydrology["water_environment_hydrology_gate"])
    gaps = []
    for category, types in CATEGORIES.items():
        for pollutant in POLLUTANTS:
            matching = [f for f in factors if f.source_type in types and f.pollutant == pollutant and not f.example]
            gaps.append({"source_category": category, "pollutant": pollutant, "status": "approved" if any(f.source_type in types and f.pollutant == pollutant for f in approved) else "candidate" if matching else "missing"})
    factor_set = build_project_factor_set(PROJECT_ID, factors, approvals, [f"{r['source_category']}:{r['pollutant']}" for r in gaps if r["status"] != "approved"])
    checks = validate_source_load_ledger(ledger)
    if checks["status"] != "passed": raise ValueError("Ledger balance failed")
    paths = {}
    def write(key, relative, sheets):
        frames = {name: frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame) for name, frame in sheets.items()}
        for name, frame in frames.items():
            if frame.empty and not len(frame.columns): frames[name] = pd.DataFrame([{"status": "no_records", "record_count": 0}]); continue
            for column in frame.select_dtypes(include="object"):
                frame[column] = frame[column].map(lambda v: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "@")) else v)
        paths[key] = _xlsx(root / relative, frames)
    scan = pd.DataFrame(state["scan"])
    evidence_frame = pd.DataFrame([e.as_dict() for e in records])
    queue = source_evidence_review_queue(records)
    factor_rows = [{**f.as_dict(), "effective_stage": factor_stage(f), "approval_status": next((a.status for a in reversed(approvals) if a.factor_id == f.factor_id), "candidate"), "eligible_real_candidate": not f.example} for f in factors]
    write("evidence", "evidence/source_evidence_inventory.xlsx", {"evidence": evidence_frame, "scan": scan})
    write("review_queue", "evidence/evidence_review_queue.xlsx", {"review_queue": queue})
    write("activity", "activity/confirmed_activity.xlsx", {"activity": [a.as_dict() for a in activities], "status": [{"records": len(activities), "meaning": "Confirmed activity only; no design-capacity substitution"}]})
    write("activity_gap", "activity/activity_gap_matrix.xlsx", {"sources": activity_gap, "categories": categories})
    write("factors", "factors/factor_candidates.xlsx", {"factors": factor_rows, "source_search": state.get("factor_sources", [{"status": "numeric_candidates_not_verified", "message": "Official source does not imply approval; examples excluded"}])})
    write("factor_comparison", "factors/factor_comparison.xlsx", {"comparison": factor_rows})
    write("factor_set", "factors/project_factor_set.xlsx", {"factor_set": [factor_set.as_dict()], "approved_factors": [f.as_dict() for f in approved], "approvals": [a.as_dict() for a in approvals]})
    write("factor_gap", "factors/factor_gap_matrix.xlsx", {"gaps": gaps})
    write("mapping", "spatial/source_reach_mapping.xlsx", {"mapping": mapping})
    spatial = gpd.GeoDataFrame(mapping, geometry=gpd.points_from_xy(sources.longitude, sources.latitude), crs=state["spatial"].get("source_crs"))
    paths["map_geojson"] = root / "spatial/source_mapping.geojson"
    spatial.to_file(paths["map_geojson"], driver="GeoJSON")
    write("ledger", "ledger/source_load_ledger_v2.xlsx", {"source_load_ledger": ledger, "balance": [checks]})
    summary = []
    for p in POLLUTANTS:
        data = ledger[ledger.pollutant.eq(p)]
        summary.append({"pollutant": p, "quantified_sources": int(data.net_emission_load.notna().sum()), "unquantified_sources": int(data.net_emission_load.isna().sum()), "measured": int(data.calculation_status.eq("measured").sum()), "reported": int(data.calculation_status.eq("reported").sum()), "factor_derived": int(data.calculation_status.eq("calculated").sum()), **{key: None if data[key].notna().sum() == 0 else float(data[key].sum()) for key in ("generated_load", "removed_load", "net_emission_load")}, "unit": "kg/day", "baseline_quantified_sources": 0, "ledger_parent": "M9A ledger version 1", "subtotal_only": True})
    write("ledger_change", "ledger/ledger_change_summary.xlsx", {"pollutants": summary})
    requests = build_data_requests()
    write("readiness", "readiness/m9b_readiness.xlsx", {"gates": [{"name": k, "value": json.dumps(v, ensure_ascii=False)} for k, v in gates.items()], "category_completeness": categories})
    write("requests", "readiness/m9a1_data_request_list.xlsx", {"requests": requests})
    facts = {"schema_version": 1, "project_id": PROJECT_ID, "parent_version": "pv_957ad45092ea", "ledger_version": 2, "factor_set": factor_set.factor_set_id, "scan": scan.status.value_counts().to_dict(), "evidence_count": len(records), "evidence_status": evidence_frame.status.value_counts().to_dict(), "linked_evidence_count": sum(bool(e.source_id) for e in records), "activity_records": len(activities), "activity_summary": activity_gap.groupby(["source_type", "status"]).size().reset_index(name="count").to_dict("records"), "project_approved_factors": len(approved), "factor_gap": gaps, "spatial": {"valid_coordinates": int(mapping.coordinate_valid.sum()), "subbasin_mapped": int(mapping.subbasin_id.notna().sum()), "reach_mapped": int(mapping.reach_id.notna().sum()), "methods": mapping.mapping_method.value_counts().to_dict(), "confidence": mapping.confidence.value_counts().to_dict()}, "ledger": summary, "ledger_balance": checks, "gates": gates, "water_quality": "planned", "hydrology_gate": hydrology["water_environment_hydrology_gate"], "hydrology_validation": hydrology["scientific_status"], "data_requests": requests.priority.value_counts().to_dict(), "limitations": ["Source accounting only; no mobilization, transport or river concentrations", "Instantaneous samples do not establish continuous emissions", "Approval is a project decision, not universal scientific validity", "Surveyed river lines require a reviewed M8B reach crosswalk", "County totals and river monitoring are not source-level activity"], "timestamp": datetime.now(timezone.utc).isoformat()}
    headings = ["M9A blocker baseline", "Evidence discovery", "Activity coverage", "Factor candidates", "Factor approvals", "Factor gaps", "Spatial attribution", "Ledger update", "Coverage", "Remaining data requests", "M9B readiness", "Limitations"]
    facts["factor_counts"] = {"candidates": sum(not f.example for f in factors), "official_source": sum(not f.example and f.source_type_reference == "official_standard" for f in factors), "local_official": sum(not f.example and f.source_type_reference == "local_official" for f in factors), "literature": sum(not f.example and f.source_type_reference == "literature" for f in factors), "approved": len(approved), "examples_blocked": sum(f.example for f in factors), "export_delivery_blocked": sum(factor_stage(f) != "generation_factor" for f in factors)}
    facts["evidence_by_source_type"] = [{"source_type": source_type, "sources": len(group), "evidence_types": pd.Series([e.evidence_type for e in records if e.source_id in set(group.source_id)], dtype=str).value_counts().to_dict()} for source_type, group in sources.groupby("source_type")]
    facts["manual_review_count"] = len(queue)
    facts["pollutant_coverage"] = {r["pollutant"]: r["quantified_sources"] / len(sources) if len(sources) else 0 for r in summary}
    facts["source_counts"] = sources.source_type.value_counts().to_dict()
    facts["coordinate_crs_status"] = "documented" if state["spatial"].get("coordinate_evidence") else "assumed_not_approved"
    facts["scientific_status"] = "real_data_diagnostic"
    sections = [{"baseline": "101 sources; no activities, approved factors or reach mapping"}, {"files": facts["scan"], "evidence": facts["evidence_status"]}, facts["activity_summary"], facts["factor_counts"], {"approved": len(approved)}, gaps, {**facts["spatial"], "coordinate_crs_status": facts["coordinate_crs_status"]}, summary, categories.to_dict("records"), requests.to_dict("records"), gates, facts["limitations"]]
    zh_headings = ["M9A 基线", "证据检索", "活动量覆盖", "候选系数", "项目审批", "系数缺口", "空间归属", "账本更新", "覆盖与全流域边界", "补资料清单", "M9B 就绪度", "限制"]
    zh_notes = ["沿用既有清单和 Source ID，不新增另一套污染源系统。", "候选不等于确认；读取失败、重复资料和非定向文件分别统计。", "只有确认且具有时间、单位和血缘的活动量进入核算。", "官方公开系数仅为候选，示例不参与真实项目。COD 不能替代 CODMn。", "批准表示项目决定采用，不表示科学上普遍正确；本流程不代替项目负责人审批。", "生活源候选不能套用于排口；缺失不填写为零。", "几何可定位不等于坐标基准已审核。最近河线不等于计算河段。", "实测出水负荷不反推产生或削减量。所有缺失保留 NA。", "点源小计不能代表全流域总量；未调查类别保留 unknown。", "P0 阻断后续计算，P1 影响可信度。请逐源补资料并保留文档定位。", "不降低 80% 覆盖门槛；保留既有水文诊断警告。", "没有实施 M9B，不进行污染物动员、输移或浓度模拟。"]
    for language in ("zh", "en"):
        path = root / f"reports/m9a1_source_evidence_closure_report_{language}.md"; path.parent.mkdir(parents=True, exist_ok=True)
        text = "# M9A.1 污染源证据闭环 / Source evidence closure\n\n"
        titles = zh_headings if language == "zh" else headings
        text += "\n\n".join(f"## {i}. {title}\n\n{zh_notes[i-1] if language == 'zh' else ''}\n\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```" for i, (title, data) in enumerate(zip(titles, sections), 1))
        text += "\n\n## References / 来源\n" + "\n".join(f"- [{s['title']}]({s['reference']}) ({s['locator']})" for s in state.get("factor_sources", []))
        text += "\n\n已停止，没有开始 M9B。 / Stopped before M9B.\n"
        path.write_text(text, encoding="utf-8"); paths[f"report_{language}"] = path
    facts["outputs"] = {k: str(p.relative_to(root)) for k, p in paths.items()}
    paths["manifest"] = _json(root / "reports/m9a1_manifest.json", facts)
    state["outputs_stale"] = False; _save_state(root, state)
    if finalize:
        from hydrolite.source_evidence_delivery import finalize_evidence_delivery
        facts.update(finalize_evidence_delivery(workspace, root, paths, facts))
    return {"status": "passed", "manifest": str(paths["manifest"]), "pollutant_delivery_model_gate": gates["pollutant_delivery_model_gate"], "facts": facts}


def run_evidence_command(command, *, source_root=None, workspace_dir=DEFAULT_WORKSPACE, output_dir=DEFAULT_OUTPUT, **review):
    if command not in COMMANDS: raise ValueError("Unknown evidence command")
    if review.get("object_id"):
        return record_review(output_dir, review["object_id"], review["action"], actor=review["actor"], comment=review["comment"], factor=command == "factor-set")
    if command in {"evidence", "readiness", "spatial-map"}:
        result = run_evidence_closure(source_root, workspace_dir=workspace_dir, output_dir=output_dir, finalize=review.get("finalize", False))
        return {k: v for k, v in result.items() if k != "facts"}
    state = read_evidence_state(output_dir)
    key = {"evidence-review": "evidence", "factor-candidates": "factors", "factor-set": "approvals"}[command]
    return {"status": "passed" if state else "output_missing", "records": len(state.get(key, [])), "output_dir": str(output_dir), "outputs_stale": state.get("outputs_stale", True)}
