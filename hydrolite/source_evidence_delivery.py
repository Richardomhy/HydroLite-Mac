"""Freeze M9A.1 derivatives through the existing version/artifact/review interfaces."""

from pathlib import Path
import shutil
import sys
import uuid

from hydrolite.water_environment import PROJECT_ID, _now, _git_commit, _json


def finalize_evidence_delivery(workspace, root, paths, facts, *, parent_version="pv_957ad45092ea", version_number=4, phase="m9a1", stage="source_evidence_completion"):
    from hydrolite.__version__ import __version__
    from hydrolite.artifact_store import register_artifact
    from hydrolite.data_lineage import add_lineage_operation
    from hydrolite.delivery_review import create_deliverable, submit_delivery, review_delivery
    from hydrolite.deliverable_manifest import write_deliverable_manifest
    from hydrolite.integrity_verification import verify_deliverable
    from hydrolite.project_versioning import create_project_version, capture_delivery_environment
    from hydrolite.runtime_db import list_project_version_records, create_run_record
    from hydrolite.workspace import read_workspace_manifest, write_workspace_manifest, calculate_file_checksum
    versions = sorted(list_project_version_records(project_id=PROJECT_ID), key=lambda r: int(r["version_number"]))
    if not versions or versions[-1]["project_version_id"] != parent_version:
        raise ValueError("Freeze requires expected parent version current; never overwrite a version")
    derived = workspace / "derived" / phase; derived.mkdir(parents=True, exist_ok=True)
    manifest = read_workspace_manifest(workspace)
    parent_datasets = [d["dataset_id"] for d in manifest.get("datasets", []) if d.get("dataset_type") == "pollution_source_inventory"]
    if not parent_datasets: raise ValueError("Registered M9A inventory lineage required")
    for kind, source in {**paths, "evidence_review_state": root / "review_state.json"}.items():
        target = derived / source.name
        if target.exists(): raise ValueError(f"Existing frozen derivative: {target.name}")
        shutil.copy2(source, target)
        checksum = calculate_file_checksum(target); dataset_id = phase + "_" + checksum[:16]
        relative = target.relative_to(workspace).as_posix()
        manifest.setdefault("datasets", []).append({"dataset_id": dataset_id, "dataset_type": kind, "logical_path": relative, "processed_path": relative, "standardized_path": relative, "checksum": checksum, "size": target.stat().st_size, "quality_status": "ready_with_warnings", "source_type": "processed_derivative", "sensitive": True})
        add_lineage_operation(parent_datasets[-1], dataset_id, stage, workspace, output_checksum=checksum, parameters={"parent_version": parent_version, "ledger_version": facts["ledger_version"], "factor_set": facts["factor_set"]})
    write_workspace_manifest(workspace, manifest)
    import yaml
    config_path = workspace / "project.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config.setdefault("water_environment", {})[stage] = {"parent_version": parent_version, "ledger_version": facts["ledger_version"], "factor_set_id": facts["factor_set"], "evidence_state": f"derived/{phase}/review_state.json", "minimum_source_coverage": 0.8, "minimum_spatial_coverage": 0.8, "minimum_reach_coverage": 0.8, "water_quality": "planned"}
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    version = create_project_version(PROJECT_ID, created_by=phase + "_workflow", description="Evidence closure with explicit unresolved activity, factor and reach gates", scenario_ids=(stage,), snapshot_mode="referenced", status=stage)
    if version["version_number"] != version_number or version["parent_version_id"] != parent_version: raise RuntimeError("Unexpected version chain")
    environment = capture_delivery_environment(version["project_version_id"])
    run_id = "run_" + uuid.uuid4().hex[:12]
    create_run_record(run_id=run_id, project_id=PROJECT_ID, project_version_id=version["project_version_id"], data_snapshot_id=version["data_snapshot_id"], configuration_snapshot_id=version["configuration_snapshot_id"], workflow_id=stage, run_name=phase + " evidence closure", run_mode="local", requested_at=_now(), started_at=_now(), finished_at=_now(), status="succeeded", progress=100, current_stage="readiness", git_commit=_git_commit(), hydrolite_version=__version__, python_version=sys.version.split()[0], environment_id=environment["environment_id"], result_status="real_data_diagnostic", legacy_unversioned=False, warnings=facts["limitations"])
    details = {"project_version": version["project_version_id"], "project_version_number": version_number, "parent_version": version["parent_version_id"], "data_snapshot_id": version["data_snapshot_id"], "configuration_snapshot_id": version["configuration_snapshot_id"], "run_id": run_id}
    facts.update(details); _json(paths["manifest"], facts)
    artifacts = [register_artifact(run_id, None, path) for path in paths.values()]
    deliverable = create_deliverable(version["project_version_id"], run_ids=[run_id], artifact_ids=[a["artifact_id"] for a in artifacts], created_by=phase + "_workflow", scientific_validation_level="real_data_diagnostic", capabilities=["water_environment_source_inventory", "water_environment_load_accounting"], warnings=[facts["gates"]["pollutant_delivery_model_gate"]], limitations=facts["limitations"], delivery_claim="analysis_report")
    submit_delivery(deliverable["deliverable_id"], actor="codex_" + phase, comment="Technical evidence-closure deliverable; no project factor approval or M9B permission implied")
    reviewed = review_delivery(deliverable["deliverable_id"], actor="codex_" + phase, comment="Automated technical review of provenance, missing-data gates and output integrity; not independent scientific review")
    details.update(deliverable_id=deliverable["deliverable_id"], delivery_review_status=reviewed["review_status"])
    facts.update(details); _json(paths["manifest"], facts); register_artifact(run_id, None, paths["manifest"]); write_deliverable_manifest(deliverable["deliverable_id"])
    integrity = verify_deliverable(deliverable["deliverable_id"])
    if integrity["status"] != "passed": raise RuntimeError(f"Integrity failed: {integrity}")
    details["integrity_status"] = "passed"
    facts.update(details); _json(paths["manifest"], facts); register_artifact(run_id, None, paths["manifest"]); write_deliverable_manifest(deliverable["deliverable_id"])
    if verify_deliverable(deliverable["deliverable_id"])["status"] != "passed": raise RuntimeError("Final integrity failed")
    return details
