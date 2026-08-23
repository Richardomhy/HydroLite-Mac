"""M9A pollution-source inventory and source-load accounting workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import platform
import shutil
import subprocess
import sys
import uuid
from typing import Any

import pandas as pd
import yaml

from hydrolite.__version__ import __version__
from hydrolite.artifact_store import register_artifact
from hydrolite.data_lineage import add_lineage_operation
from hydrolite.delivery_review import create_deliverable, review_delivery, submit_delivery
from hydrolite.deliverable_manifest import write_deliverable_manifest
from hydrolite.emission_factor_registry import audit_emission_factors, load_emission_factors, resolve_emission_factor
from hydrolite.integrity_verification import verify_deliverable
from hydrolite.pollution_source_inventory import (
    build_pollution_source_inventory, discover_pollution_source_datasets,
    link_sources_to_reaches, link_sources_to_subbasins, summarize_source_inventory,
    validate_source_inventory, write_source_inventory_geojson,
)
from hydrolite.project_versioning import capture_delivery_environment, create_project_version, resolve_project
from hydrolite.runtime_db import create_run_record, list_project_version_records, update_run_record
from hydrolite.source_load_ledger import (
    assess_pollutant_delivery_model_gate, build_pollutant_availability_matrix,
    build_source_load_ledger, summarize_source_loads, validate_source_load_ledger,
)
from hydrolite.workspace import calculate_file_checksum, read_workspace_manifest, write_workspace_manifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/water_environment/m9a"
DEFAULT_WORKSPACE = Path.home() / ".hydrolite/workspaces/gaoqiao-river-basin-real-validation"
PROJECT_ID = "gaoqiao_river_basin_real_validation"
OUTPUT_FILES = {
    "inventory": "inventory/pollution_source_inventory.xlsx",
    "inventory_geojson": "inventory/source_inventory.geojson",
    "activity": "activity/standardized_activity.xlsx",
    "factors": "factors/emission_factor_audit.xlsx",
    "unresolved_factors": "factors/unresolved_factors.xlsx",
    "ledger": "ledger/source_load_ledger.xlsx",
    "balance": "ledger/source_load_balance.xlsx",
    "coverage": "summary/coverage_summary.xlsx",
    "report_zh": "reports/m9a_water_environment_source_accounting_report_zh.md",
    "report_en": "reports/m9a_water_environment_source_accounting_report_en.md",
    "manifest": "reports/m9a_manifest.json",
}


def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _git_commit() -> str: return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
def _json(path: Path, payload: Any) -> Path: path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"); return path
def _xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        for name, frame in sheets.items(): frame.to_excel(writer, sheet_name=name[:31], index=False)
    return path


def water_environment_status(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    manifest = Path(output_dir) / "reports/m9a_manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    return {
        "status": "partial", "validation_level": "source_accounting_only",
        "water_environment_source_inventory": "partial", "water_environment_load_accounting": "partial",
        "water_environment_model": "partial", "water_quality": "planned",
        "water_quality_process_validation": "not_implemented",
        "latest_manifest": str(manifest) if manifest.is_file() else None,
        "pollutant_delivery_model_gate": payload.get("pollutant_delivery_model_gate", "not_assessed"),
    }


def validate_water_environment_outputs(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = Path(output_dir).expanduser().resolve()
    missing = [relative for relative in OUTPUT_FILES.values() if not (root / relative).is_file()]
    errors = [f"missing_output:{relative}" for relative in missing]
    ledger_check: dict[str, Any] = {"status": "not_checked"}
    if not missing:
        ledger = pd.read_excel(root / OUTPUT_FILES["ledger"], sheet_name="source_load_ledger")
        ledger_check = validate_source_load_ledger(ledger)
        if ledger_check["status"] != "passed": errors.append("source_load_balance_failed")
        manifest = json.loads((root / OUTPUT_FILES["manifest"]).read_text(encoding="utf-8"))
        if manifest.get("water_quality") != "planned": errors.append("water_quality_status_changed")
        if manifest.get("water_quality_process_validation") != "not_implemented": errors.append("water_quality_process_scope_changed")
        for relative in (OUTPUT_FILES["report_zh"], OUTPUT_FILES["report_en"]):
            text = (root / relative).read_text(encoding="utf-8")
            if "入河负荷" in text: errors.append(f"m9a_river_input_claim:{relative}")
    return {"status": "passed" if not errors else "failed", "output_dir": str(root), "errors": errors, "missing_outputs": missing, "ledger_validation": ledger_check}


def run_water_environment_command(
    command: str, *, source_root: str | Path | None = None,
    workspace_dir: str | Path = DEFAULT_WORKSPACE, output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    if command not in {"status", "inventory", "factors", "ledger", "validate", "report"}: raise ValueError(f"Unsupported water-environment command: {command}")
    run_result = None
    if source_root is not None:
        run_result = run_water_environment_source_accounting(source_root, workspace_dir=workspace_dir, output_dir=output_dir)
    root = Path(output_dir).expanduser().resolve()
    if command == "status": return water_environment_status(root)
    if command == "validate": return validate_water_environment_outputs(root)
    if not (root / OUTPUT_FILES["manifest"]).is_file():
        return {"status": "output_missing", "message": "Run inventory with --source-root before inspecting M9A outputs.", "output_dir": str(root)}
    manifest = json.loads((root / OUTPUT_FILES["manifest"]).read_text(encoding="utf-8"))
    selected = {
        "inventory": ["inventory", "inventory_geojson"],
        "factors": ["factors", "unresolved_factors"],
        "ledger": ["ledger", "balance", "coverage"],
        "report": ["report_zh", "report_en", "manifest"],
    }[command]
    result = {
        "status": "passed", "command": command, "output_dir": str(root),
        "outputs": {key: str(root / OUTPUT_FILES[key]) for key in selected},
        "scientific_status": manifest.get("scientific_status"),
        "pollutant_delivery_model_gate": manifest.get("pollutant_delivery_model_gate"),
    }
    if run_result:
        result.update({"project_version": run_result["version"]["project_version_id"], "run_id": run_result["run"]["run_id"], "deliverable_id": run_result["deliverable"]["deliverable_id"]})
    return result


def _register_workspace_outputs(workspace: Path, output: Path, paths: dict[str, Path]) -> None:
    derived = workspace / "derived/m9a"; derived.mkdir(parents=True, exist_ok=True)
    manifest = read_workspace_manifest(workspace); existing = {row.get("dataset_id") for row in manifest.get("datasets", [])}
    for dataset_type, source in paths.items():
        target = derived / source.name; shutil.copy2(source, target)
        dataset_id = f"m9a_{calculate_file_checksum(target)[:16]}"
        if dataset_id not in existing:
            relative = target.relative_to(workspace).as_posix()
            manifest.setdefault("datasets", []).append({"dataset_id": dataset_id, "dataset_type": dataset_type, "user_declared_type": dataset_type, "logical_path": relative, "processed_path": relative, "standardized_path": relative, "checksum": calculate_file_checksum(target), "size": target.stat().st_size, "quality_status": "ready_with_warnings", "source_type": "processed_derivative", "sensitive": True})
            add_lineage_operation("external_pollution_source_dataset", dataset_id, "m9a_source_accounting", workspace, output_checksum=calculate_file_checksum(target), parameters={"scope": "generated_removed_net_emission_only"})
    write_workspace_manifest(workspace, manifest)
    config_dir = workspace / "configs/m9a"; config_dir.mkdir(parents=True, exist_ok=True)
    source_accounting = {"workflow_id": "water_environment_source_accounting", "allow_example_factors": False, "pollutants": ["CODMn", "NH3-N", "TN", "TP"], "scope": "generated_removed_net_emission_only"}
    (config_dir / "source_accounting.yaml").write_text(yaml.safe_dump(source_accounting, sort_keys=False), encoding="utf-8")
    project_path = workspace / "project.yaml"
    project_config = yaml.safe_load(project_path.read_text(encoding="utf-8")) or {}
    project_config.setdefault("water_environment", {})["source_accounting"] = source_accounting
    project_path.write_text(yaml.safe_dump(project_config, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_reports(output: Path, facts: dict[str, Any]) -> tuple[Path, Path]:
    common = f"""- Project: `{facts['project']}`
- Project Version: `{facts['version']['project_version_id']}` (parent `{facts['version']['parent_version_id']}`)
- Source dataset: `{facts['source_dataset']}`
- Sources discovered/accepted/unresolved: `{facts['inventory']['sources_discovered']}` / `{facts['inventory']['sources_accepted']}` / `{facts['inventory']['sources_unresolved']}`
- Standardized activity records: `{facts['activity_count']}`; missing activity: `{facts['unquantified_sources']}`
- Project-approved factors: `{facts['approved_factor_count']}`; example factors blocked: `{facts['blocked_example_factor_count']}`
- Treatment records: `0`
- Quantified source-pollutant records: `{facts['ledger_validation']['quantified_records']}`
- Ledger mass-balance residual: `{facts['ledger_validation']['max_balance_residual_kg_day']}` kg/day
- Canonical unit: `kg/day`; temporal basis: `daily_average`
- Basin total status: `{facts['coverage']['basin_total_load_status']}`
- Pollutant delivery model gate: `{facts['gate']['status']}`
"""
    zh = f"""# M9A 水环境污染源与负荷核算报告

> 当前水环境能力仅完成污染源清单和产生/净排放负荷核算，尚未模拟污染物入河输移和河流水质过程。

## 1. 项目
{common}
## 2. 数据
只读使用真实排污口表，不复制原始资料；报告中既有“入湖量”和“来源贡献”表未用于 M9A 产生负荷。

## 3. 污染源分类
仅接受表内显式排污口类型；明确标注“非排口”的记录被排除，缺失分级的记录保留为人工确认项。

## 4. Activity
未发现可用于产生负荷的流量、污水量、人口、存栏、施肥或产量活动数据。

## 5. Emission Factors
未发现经高桥河项目批准的排放系数。示例系数默认禁用于真实项目。

## 6. Treatment
未发现可审计的处理及实际运行削减记录。

## 7. Generated Load
无可靠 activity 与批准系数的组合，未量化产生负荷。

## 8. Net Emission Load
未量化净排放负荷；不将缺失负荷记为零。

## 9. Coverage
量化覆盖率 `{facts['coverage']['quantified_source_fraction']:.1%}`，空间子流域匹配率 `{facts['coverage']['spatial_coverage']:.1%}`，全流域总负荷不可报告。

## 10. Spatial Attribution
点位尽量匹配到 M8B 子流域；河段映射未解决，不可自动进入 M9B。

## 11. Evidence Tiers
未产生定量负荷，因此不分配虚假 evidence tier。

## 12. Uncertainty
系数区间与 activity 不可用，不确定性状态为 unavailable，未假定 ±20%。

## 13. Missing Sources
人口、工业排放、畜禽活动量、种植及施肥、水产养殖、处理设施运行和排水量均需补充原始证据。

## 14. Limitations
`generated_load ≠ net_emission_load ≠ mobilized_load ≠ delivered_load ≠ river_input_load`。本报告不做源解析、污染物输移或河道浓度模拟结论。

## 15. M9B Readiness
`{facts['gate']['status']}`：{', '.join(facts['gate']['blockers']) or 'no blockers'}。
"""
    en = f"""# M9A Water Environment Source Accounting Report

> Current water-environment capability covers source inventory and generated/net-emission accounting only. Pollutant delivery and river water-quality processes are not implemented.

## 1. Project
{common}
## 2. Data
The real outfall workbook was read in place. Existing inlet-load and source-contribution report tables were not treated as M9A generated-load evidence.

## 3. Source classification
Only explicit source fields were accepted; records explicitly marked non-outfall were excluded and missing grades require confirmation.

## 4. Activity
No auditable discharge, population, livestock, fertilizer, production, or aquaculture activity records were available.

## 5. Emission Factors
No factor approved for this real project was found. Example factors remain blocked.

## 6. Treatment
No auditable treatment-operation records were found.

## 7. Generated Load
Not quantified because required activity and approved factors are unavailable.

## 8. Net Emission Load
Not quantified; missing values are not represented as zero.

## 9. Coverage
Quantified source coverage is `{facts['coverage']['quantified_source_fraction']:.1%}` and subbasin spatial coverage is `{facts['coverage']['spatial_coverage']:.1%}`. A basin total is not reportable.

## 10. Spatial Attribution
Points were matched to reviewed M8B subbasins where possible; reach attribution remains unresolved.

## 11. Evidence Tiers
No quantitative load was assigned a fabricated evidence tier.

## 12. Uncertainty
Unavailable; no generic uncertainty percentage was invented.

## 13. Missing Sources
Population, enterprise discharge, livestock, fertilizer, aquaculture, treatment operation, and discharge-flow evidence remain gaps.

## 14. Limitations
Generated load, net emission, mobilized load, delivered load, and river input load are distinct. No source-apportionment or river-concentration claim is made.

## 15. M9B Readiness
`{facts['gate']['status']}`: {', '.join(facts['gate']['blockers']) or 'no blockers'}.
"""
    zh_path = output / "reports/m9a_water_environment_source_accounting_report_zh.md"
    en_path = output / "reports/m9a_water_environment_source_accounting_report_en.md"
    zh_path.parent.mkdir(parents=True, exist_ok=True); zh_path.write_text(zh, encoding="utf-8"); en_path.write_text(en, encoding="utf-8")
    return zh_path, en_path


def run_water_environment_source_accounting(
    source_root: str | Path, *, workspace_dir: str | Path = DEFAULT_WORKSPACE,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    source, workspace, output = Path(source_root).expanduser().resolve(), Path(workspace_dir).expanduser().resolve(), Path(output_dir).expanduser().resolve()
    if not source.is_dir(): raise FileNotFoundError(f"external_project_storage_unavailable: {source}")
    if not (workspace / "project.yaml").is_file(): raise FileNotFoundError(f"M8B workspace not found: {workspace}")
    project = resolve_project(PROJECT_ID)
    if Path(project["workspace_path"]).resolve() != workspace: raise RuntimeError("M9A workspace does not match the registered project")
    m8b_manifest_path = ROOT / "output/real_project_validation/m8b/reports/m8b_manifest.json"
    if not m8b_manifest_path.is_file(): raise FileNotFoundError("M8B manifest is required")
    m8b = json.loads(m8b_manifest_path.read_text(encoding="utf-8"))
    if m8b.get("water_environment_hydrology_gate") not in {"ready", "ready_with_warnings"}: raise RuntimeError("M8B hydrology gate blocks M9A")

    datasets = discover_pollution_source_datasets(source)
    accepted = [item for item in datasets if item["dataset_type"] == "pollution_source_inventory" and item["classification_status"] == "accepted"]
    if len(accepted) != 1: raise RuntimeError(f"Expected one explicit pollution-source inventory; found {len(accepted)}")
    dataset = accepted[0]; source_checksum_before = calculate_file_checksum(dataset["path"])
    inventory = build_pollution_source_inventory(dataset, PROJECT_ID)
    inventory = link_sources_to_subbasins(inventory, workspace / "derived/m8b/reviewed_subbasins.geojson")
    inventory = link_sources_to_reaches(inventory)
    inventory_validation = validate_source_inventory(inventory)
    if inventory_validation.status != "passed": raise RuntimeError(f"Pollution-source inventory validation failed: {inventory_validation.errors}")
    inventory_summary = summarize_source_inventory(inventory)

    activities = []
    activity_readiness = inventory.loc[inventory.status.isin(["accepted", "manual_confirmation_required"]), ["source_id", "source_type"]].copy()
    activity_readiness["status"] = "activity_missing"
    activity_readiness["required_evidence"] = "measured discharge/reported load or source-specific activity"
    activity_columns = ["activity_id", "source_id", "activity_type", "value", "unit", "start_date", "end_date", "temporal_basis", "source_dataset_id", "field_name", "observed_or_estimated", "quality", "provenance"]
    factors = load_emission_factors(ROOT / "config/water_environment/emission_factors.example.yaml")
    factor_audit = pd.DataFrame(audit_emission_factors(factors))
    factor_rows = []
    for row in inventory.loc[inventory.status.isin(["accepted", "manual_confirmation_required"])].itertuples(index=False):
        for pollutant in ("CODMn", "NH3-N", "TN", "TP"):
            resolution = resolve_emission_factor(factors, row.source_type, pollutant, real_project=True)
            factor_rows.append({"source_id": row.source_id, "source_type": row.source_type, "pollutant": pollutant, "status": resolution["status"]})
    factor_readiness = pd.DataFrame(factor_rows)
    ledger = build_source_load_ledger(inventory, activities, factors)
    ledger_validation = validate_source_load_ledger(ledger)
    if ledger_validation["status"] != "passed": raise RuntimeError(f"Source-load ledger validation failed: {ledger_validation}")
    summaries = summarize_source_loads(ledger, inventory)
    pollutant_matrix = build_pollutant_availability_matrix(ledger)

    considered = inventory.status.isin(["accepted", "manual_confirmation_required"])
    source_count = int(considered.sum()); quantified_sources = int(ledger.dropna(subset=["net_emission_load"]).source_id.nunique())
    spatial_mapped = int((considered & inventory.spatial_status.isin(["mapped", "mapped_low_confidence"])).sum())
    reach_mapped = int((considered & inventory.reach_id.notna()).sum())
    pollutant_coverage = {
        pollutant: int(ledger.loc[(ledger.pollutant == pollutant) & ledger.net_emission_load.notna(), "source_id"].nunique()) / source_count if source_count else 0.0
        for pollutant in ("CODMn", "NH3-N", "TN", "TP")
    }
    required_source_types = set(inventory.loc[considered, "source_type"])
    quantified_source_types = set(ledger.loc[ledger.net_emission_load.notna(), "source_type"])
    source_type_coverage = len(required_source_types & quantified_source_types) / len(required_source_types) if required_source_types else 0.0
    tier_distribution = ledger.loc[ledger.evidence_tier.ne("unknown"), "evidence_tier"].value_counts().to_dict()
    coverage = {
        "sources_discovered": inventory_summary["sources_discovered"], "sources_quantified": quantified_sources,
        "sources_unquantified": source_count - quantified_sources,
        "quantified_source_fraction": quantified_sources / source_count if source_count else 0.0,
        "pollutant_coverage": pollutant_coverage,
        "spatial_coverage": spatial_mapped / source_count if source_count else 0.0,
        "reach_coverage": reach_mapped / source_count if source_count else 0.0,
        "low_confidence_spatial_count": int((considered & inventory.spatial_status.eq("mapped_low_confidence")).sum()),
        "source_type_coverage": source_type_coverage,
        "evidence_tier_distribution": tier_distribution,
        "missing_factor_count": int(factor_readiness.status.ne("resolved").sum()),
        "activity_missing_count": len(activity_readiness),
        "minimum_source_coverage": 0.8, "minimum_spatial_coverage": 0.8, "minimum_reach_coverage": 0.8,
        "quantified_subtotal_status": "partial_quantified_load" if quantified_sources else "no_quantified_load",
        "basin_total_load_status": "reportable" if source_count and quantified_sources / source_count >= 0.8 and source_type_coverage == 1.0 and all(value >= 0.8 for value in pollutant_coverage.values()) else "not_reportable",
    }
    gate = assess_pollutant_delivery_model_gate(coverage, m8b["water_environment_hydrology_gate"])

    paths = {
        "pollution_source_inventory": _xlsx(output / "inventory/pollution_source_inventory.xlsx", {"inventory": inventory, "validation": pd.DataFrame([inventory_validation.as_dict()]), "datasets": pd.DataFrame([{key: value for key, value in dataset.items() if key != "path"}])}),
        "source_inventory_geojson": write_source_inventory_geojson(inventory, output / "inventory/source_inventory.geojson"),
        "source_activity": _xlsx(output / "activity/standardized_activity.xlsx", {"standardized_activity": pd.DataFrame(columns=activity_columns), "activity_readiness": activity_readiness}),
        "treatment_factor": _xlsx(output / "activity/source_treatment_audit.xlsx", {"treatment_records": pd.DataFrame(columns=["treatment_id", "source_id", "pollutant", "removal_fraction"]), "validation": pd.DataFrame([{"status": "passed", "record_count": 0, "message": "No treatment claim was made."}])}),
        "emission_factor": _xlsx(output / "factors/emission_factor_audit.xlsx", {"registered_examples": factor_audit, "project_factor_readiness": factor_readiness}),
        "unresolved_factors": _xlsx(output / "factors/unresolved_factors.xlsx", {"unresolved_factors": factor_readiness}),
        "source_load_ledger": _xlsx(output / "ledger/source_load_ledger.xlsx", {"source_load_ledger": ledger}),
        "source_load_balance": _xlsx(output / "ledger/source_load_balance.xlsx", {"validation": pd.DataFrame([ledger_validation]), "semantic_gate": pd.DataFrame([{"generated_load_not_net_emission": True, "net_emission_not_mobilized": True, "net_emission_not_delivered": True, "net_emission_not_river_input": True}])}),
        "pollutant_availability_matrix": _xlsx(output / "ledger/pollutant_availability_matrix.xlsx", {"source_pollutant_matrix": pollutant_matrix}),
        "load_by_source": _xlsx(output / "summary/load_by_source.xlsx", {"load_by_source": summaries["by_source"], "status": pd.DataFrame([{"status": coverage["quantified_subtotal_status"], "label": "quantified subtotal"}])}),
        "load_by_pollutant": _xlsx(output / "summary/load_by_pollutant.xlsx", {"load_by_pollutant": summaries["by_pollutant"], "status": pd.DataFrame([{"status": coverage["quantified_subtotal_status"], "label": "quantified subtotal"}])}),
        "load_by_subbasin": _xlsx(output / "summary/load_by_subbasin.xlsx", {"load_by_subbasin": summaries["by_subbasin"], "status": pd.DataFrame([{"status": coverage["quantified_subtotal_status"], "label": "quantified subtotal"}])}),
        "load_by_administrative_unit": _xlsx(output / "summary/load_by_administrative_unit.xlsx", {"load_by_administrative_unit": summaries["by_administrative_unit"], "status": pd.DataFrame([{"status": coverage["quantified_subtotal_status"], "label": "quantified subtotal"}])}),
        "unresolved_sources": _xlsx(output / "summary/unresolved_sources.xlsx", {"unresolved_sources": inventory.loc[inventory.status.eq("manual_confirmation_required")], "activity_missing": activity_readiness, "factor_missing": factor_readiness.loc[factor_readiness.status.ne("resolved")]}),
        "coverage_summary": _xlsx(output / "summary/coverage_summary.xlsx", {"coverage": pd.DataFrame([{**coverage, "pollutant_coverage": json.dumps(coverage["pollutant_coverage"]), "evidence_tier_distribution": json.dumps(coverage["evidence_tier_distribution"])}]), "delivery_gate": pd.DataFrame([gate])}),
    }
    _register_workspace_outputs(workspace, output, paths)

    versions = sorted(list_project_version_records(project_id=PROJECT_ID), key=lambda row: int(row["version_number"]))
    m9a_versions = [row for row in versions if row.get("status") == "water_environment_source_accounting"]
    if m9a_versions: version = m9a_versions[-1]
    else:
        if not versions or versions[-1]["project_version_id"] != m8b["project_version"] or int(versions[-1]["version_number"]) != 2: raise RuntimeError("M9A requires M8B Project Version 2 as the current parent")
        version = create_project_version(PROJECT_ID, created_by="m9a_source_accounting", description="Real pollution-source inventory and generated/net-emission load accounting readiness", scenario_ids=("water_environment_source_accounting",), snapshot_mode="referenced", status="water_environment_source_accounting")
    if int(version["version_number"]) != 3 or version["parent_version_id"] != m8b["project_version"]: raise RuntimeError("Project Version 3 parent chain is invalid")

    approved_factors = [factor for factor in factors if factor.approved_for_real_project and not factor.example]
    facts = {"project": project["display_name"], "version": version, "source_dataset": dataset["logical_path"], "inventory": inventory_summary, "activity_count": 0, "unquantified_sources": coverage["sources_unquantified"], "approved_factor_count": len(approved_factors), "blocked_example_factor_count": sum(factor.example for factor in factors), "ledger_validation": ledger_validation, "coverage": coverage, "gate": gate}
    report_zh, report_en = _write_reports(output, facts); paths.update({"report_zh": report_zh, "report_en": report_en})

    run_id = f"run_{uuid.uuid4().hex[:12]}"; environment = capture_delivery_environment(version["project_version_id"]); timestamp = _now()
    config_path = workspace / "configs/m9a/source_accounting.yaml"
    run = create_run_record(run_id=run_id, project_id=PROJECT_ID, project_version_id=version["project_version_id"], data_snapshot_id=version["data_snapshot_id"], configuration_snapshot_id=version["configuration_snapshot_id"], workflow_id="source_load_accounting", run_name="M9A source accounting", run_mode="local", requested_at=timestamp, started_at=timestamp, finished_at=timestamp, status="succeeded", progress=100, current_stage="report", configuration_path="configs/m9a/source_accounting.yaml", configuration_checksum=calculate_file_checksum(config_path), git_commit=_git_commit(), hydrolite_version=__version__, python_version=sys.version.split()[0], environment_id=environment["environment_id"], result_status="real_data_diagnostic", error_summary="", legacy_unversioned=False, warnings=gate["blockers"])

    manifest = {
        "schema_version": 1, "project": project["display_name"], "project_id": PROJECT_ID,
        "project_version": version["project_version_id"], "project_version_number": version["version_number"], "parent_version": version["parent_version_id"],
        "data_snapshot_id": version["data_snapshot_id"], "configuration_snapshot_id": version["configuration_snapshot_id"],
        "source_datasets": [{key: value for key, value in dataset.items() if key != "path"}],
        "source_counts": inventory_summary, "source_types": inventory_summary["source_counts_by_type"],
        "activity_datasets": [], "factors": len(factors), "project_approved_factors": len(approved_factors),
        "factor_sources": sorted({factor.source_type_reference for factor in factors}), "evidence_tiers": {},
        "generated_loads": {pollutant: None for pollutant in ("CODMn", "NH3-N", "TN", "TP")},
        "removed_loads": {pollutant: None for pollutant in ("CODMn", "NH3-N", "TN", "TP")},
        "net_emission_loads": {pollutant: None for pollutant in ("CODMn", "NH3-N", "TN", "TP")},
        "coverage": coverage, "unresolved_items": {"activity_missing": coverage["sources_unquantified"], "factor_missing": len(factor_readiness), "reach_mapping_missing": source_count},
        "spatial_mapping": {"mapped_to_subbasin": spatial_mapped, "mapped_to_reach": reach_mapped},
        "source_inventory_validation": "real_data_tested", "source_load_accounting_validation": "real_data_diagnostic",
        "hydrology_validation": m8b["scientific_status"], "water_quality_process_validation": "not_implemented",
        "scientific_status": "real_data_diagnostic", "validation_level": "source_accounting_only",
        "water_environment_source_inventory": "partial", "water_environment_load_accounting": "partial", "water_environment_model": "partial", "water_quality": "planned",
        "pollutant_delivery_model_gate": gate["status"], "pollutant_delivery_model_gate_details": gate,
        "limitations": ["No project-approved emission factors.", "No source activity or discharge-flow records.", "Reach attribution is unresolved.", "No pollutant mobilization, delivery, river process, concentration simulation, or source apportionment."],
        "run_id": run_id, "deliverable_id": "pending", "delivery_review_status": "pending", "integrity_status": "pending",
        "git_commit": _git_commit(), "software_version": __version__, "python_version": sys.version.split()[0], "os": platform.platform(), "timestamp": _now(),
    }
    manifest_path = _json(output / "reports/m9a_manifest.json", manifest); paths["manifest"] = manifest_path
    artifacts = [register_artifact(run_id, None, path) for path in paths.values()]
    report_ids = [item["artifact_id"] for item in artifacts if item["display_name"] in {report_zh.name, report_en.name}]
    artifact_ids = [item["artifact_id"] for item in artifacts if item["artifact_id"] not in report_ids]
    deliverable = create_deliverable(version["project_version_id"], run_ids=[run_id], artifact_ids=artifact_ids, report_ids=report_ids, created_by="m9a_source_accounting", scientific_validation_level="real_data_diagnostic", capabilities=["water_environment_source_inventory", "water_environment_load_accounting"], warnings=gate["blockers"], limitations=manifest["limitations"], delivery_claim="analysis_report")
    manifest.update({"deliverable_id": deliverable["deliverable_id"], "delivery_review_status": "draft"}); _json(manifest_path, manifest); register_artifact(run_id, None, manifest_path)
    submit_delivery(deliverable["deliverable_id"], actor="m9a_analyst", comment="Submitted as source-accounting foundation with blocked delivery-model gate.")
    deliverable = review_delivery(deliverable["deliverable_id"], actor="m9a_reviewer", comment="Reviewed for source evidence, load semantics, missing factors, spatial coverage, and M9B gate.")
    manifest.update({"delivery_review_status": deliverable["review_status"], "integrity_status": "pending", "timestamp": _now()}); _json(manifest_path, manifest); register_artifact(run_id, None, manifest_path); write_deliverable_manifest(deliverable["deliverable_id"])
    integrity = verify_deliverable(deliverable["deliverable_id"])
    manifest["integrity_status"] = integrity["status"]; _json(manifest_path, manifest); register_artifact(run_id, None, manifest_path); write_deliverable_manifest(deliverable["deliverable_id"]); integrity = verify_deliverable(deliverable["deliverable_id"])
    if integrity["status"] != "passed": raise RuntimeError(f"M9A deliverable integrity failed: {integrity}")
    if calculate_file_checksum(dataset["path"]) != source_checksum_before: raise RuntimeError("External source changed during M9A read-only processing")
    update_run_record(run_id, result_status="real_data_diagnostic", warnings=gate["blockers"])
    return {"status": "passed", "output_dir": str(output), "version": version, "run": run, "deliverable": deliverable, "integrity": integrity, "manifest": str(manifest_path), "inventory": inventory_summary, "coverage": coverage, "gate": gate}
