"""Local delivery review workflow kept separate from scientific validation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json
import uuid

from hydrolite.artifact_store import freeze_artifacts
from hydrolite.deliverable_manifest import write_deliverable_manifest, write_report_delivery_metadata
from hydrolite.integrity_verification import verify_artifact, verify_deliverable
from hydrolite.product_status import VALIDATION_LEVELS, get_product_feature_status
from hydrolite.runtime_db import (
    create_audit_event_record,
    create_deliverable_record,
    create_review_record,
    create_warning_acknowledgment_record,
    get_artifact_record,
    get_configuration_snapshot_record,
    get_data_snapshot_record,
    get_deliverable_record,
    get_project_version_record,
    get_run_record,
    list_artifact_records,
    list_deliverable_records,
    list_review_records,
    list_warning_acknowledgment_records,
    update_deliverable_record,
)


DELIVERY_REVIEW_STATUSES = {
    "draft", "submitted_for_review", "changes_requested", "reviewed",
    "approved_for_delivery", "rejected", "superseded", "archived",
}
ROLE_ACTIONS = {
    "analyst": {"create", "submit"},
    "technical_reviewer": {"review", "request_changes"},
    "project_manager": {"approve", "reject", "supersede", "archive"},
    "viewer": set(),
}
TRANSITIONS = {
    "submit": ({"draft", "changes_requested"}, "submitted_for_review"),
    "review": ({"submitted_for_review"}, "reviewed"),
    "request_changes": ({"submitted_for_review", "reviewed"}, "changes_requested"),
    "approve": ({"reviewed"}, "approved_for_delivery"),
    "reject": ({"submitted_for_review", "reviewed"}, "rejected"),
    "supersede": ({"approved_for_delivery"}, "superseded"),
    "archive": ({"rejected", "superseded", "approved_for_delivery"}, "archived"),
}
CRITICAL_WARNINGS = {
    "REAL_DATA_VALIDATION_MISSING", "XAI_IMPORTANCE_UNSTABLE", "LONG_HORIZON_LOW_SKILL",
    "GEE_COMPUTE_AUTH_UNAVAILABLE", "LOW_CONFIDENCE_MAPPING",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _warning_code(value: Any) -> str:
    return str(value.get("warning_code") or value.get("code") or "") if isinstance(value, dict) else str(value)


def _audit(deliverable: dict[str, Any], actor: str, action: str, summary: str, metadata: dict | None = None) -> None:
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=_now(), project_id=deliverable["project_id"],
        project_version_id=deliverable["project_version_id"], deliverable_id=deliverable["deliverable_id"],
        actor=actor, action=action, object_type="deliverable", object_id=deliverable["deliverable_id"],
        summary=summary, metadata=metadata or {},
    )


def create_deliverable(
    project_version_id: str, *, run_ids: Iterable[str] = (), artifact_ids: Iterable[str] = (),
    report_ids: Iterable[str] = (), created_by: str = "local_user",
    scientific_validation_level: str = "framework_ready", capabilities: Iterable[str] = (),
    warnings: Iterable[Any] = (), limitations: Iterable[str] = (),
    delivery_claim: str = "analysis_report", supersedes: str = "",
) -> dict[str, Any]:
    if scientific_validation_level not in VALIDATION_LEVELS:
        raise ValueError(f"Invalid scientific validation level: {scientific_validation_level}")
    version = get_project_version_record(project_version_id)
    if not version:
        raise KeyError(f"Unknown project version: {project_version_id}")
    capabilities = tuple(capabilities)
    warning_values = list(warnings)
    limitation_values = list(limitations)
    if scientific_validation_level == "synthetic_demo" and "REAL_DATA_VALIDATION_MISSING" not in map(_warning_code, warning_values):
        warning_values.append("REAL_DATA_VALIDATION_MISSING")
    if "flood_susceptibility_xai" in capabilities and "XAI_IMPORTANCE_UNSTABLE" not in map(_warning_code, warning_values):
        warning_values.append("XAI_IMPORTANCE_UNSTABLE")
    if "flood_susceptibility" in capabilities:
        for limitation in ("Susceptibility is not risk.", "Complex-model value-added is not demonstrated."):
            if limitation not in limitation_values: limitation_values.append(limitation)
    deliverable_id = f"del_{uuid.uuid4().hex[:12]}"
    record = create_deliverable_record(
        deliverable_id=deliverable_id,
        project_id=version["project_id"],
        project_version_id=project_version_id,
        run_ids=list(run_ids),
        artifact_ids=list(artifact_ids),
        report_ids=list(report_ids),
        created_by=created_by,
        review_status="draft",
        scientific_validation_level=scientific_validation_level,
        capabilities=list(capabilities),
        warnings=warning_values,
        limitations=limitation_values,
        manifest_path="",
        manifest_hash="",
        package_hash="",
        supersedes=supersedes,
        provenance={
            "delivery_claim": delivery_claim,
            "scientific_status_is_independent": True,
            "authenticated_signature": False,
        },
    )
    write_deliverable_manifest(deliverable_id)
    record = get_deliverable_record(deliverable_id) or record
    _audit(record, created_by, "deliverable_created", "Draft deliverable created.")
    return record


def list_deliverables(project_id: str | None = None) -> list[dict[str, Any]]:
    return list_deliverable_records(**({"project_id": project_id} if project_id else {}))


def acknowledge_warning(deliverable_id: str, warning_code: str, *, actor: str, comment: str) -> dict[str, Any]:
    deliverable = get_deliverable_record(deliverable_id)
    if not deliverable:
        raise KeyError(deliverable_id)
    codes = {_warning_code(value) for value in deliverable.get("warnings", [])}
    if warning_code not in codes:
        raise ValueError(f"Warning is not present on deliverable: {warning_code}")
    if not actor.strip() or not comment.strip():
        raise ValueError("Warning acknowledgment requires actor and comment")
    existing = [row for row in list_warning_acknowledgment_records(deliverable_id=deliverable_id) if row["warning_code"] == warning_code]
    if existing:
        return existing[-1]
    record = create_warning_acknowledgment_record(
        acknowledgment_id=f"ack_{uuid.uuid4().hex[:12]}", deliverable_id=deliverable_id,
        warning_code=warning_code, acknowledged_by=actor, acknowledged_at=_now(), comment=comment,
    )
    _audit(deliverable, actor, "warning_acknowledged", f"Warning {warning_code} acknowledged.", {"warning_code": warning_code})
    write_deliverable_manifest(deliverable_id)
    return record


def assess_delivery_readiness(deliverable_id: str) -> dict[str, Any]:
    deliverable = get_deliverable_record(deliverable_id)
    if not deliverable:
        return {"status": "blocked", "blockers": ["deliverable_missing"], "warnings": [], "required_actions": ["Create deliverable"]}
    blockers: list[str] = []
    advisory: list[str] = []
    version = get_project_version_record(deliverable.get("project_version_id"))
    if not version:
        blockers.append("project_version_missing")
    if not version or not get_data_snapshot_record(version.get("data_snapshot_id")):
        blockers.append("data_snapshot_missing")
    if not version or not get_configuration_snapshot_record(version.get("configuration_snapshot_id")):
        blockers.append("configuration_snapshot_missing")
    runs = [get_run_record(run_id) for run_id in deliverable.get("run_ids", [])]
    if not runs:
        blockers.append("completed_run_missing")
    elif any(not run or run.get("status") not in {"succeeded", "success", "completed"} for run in runs):
        blockers.append("run_not_completed")
    if any(run and bool(run.get("legacy_unversioned", True)) for run in runs):
        blockers.append("legacy_unversioned_run_not_deliverable")
    if any(run and run.get("project_version_id") != deliverable.get("project_version_id") for run in runs):
        blockers.append("run_project_version_mismatch")
    artifact_ids = [*deliverable.get("artifact_ids", []), *deliverable.get("report_ids", [])]
    if not artifact_ids:
        blockers.append("artifact_set_missing")
    elif any(verify_artifact(artifact_id)["status"] != "passed" for artifact_id in artifact_ids):
        blockers.append("artifact_integrity_invalid")
    if not deliverable.get("report_ids"):
        blockers.append("report_missing")
    if not deliverable.get("scientific_validation_level"):
        blockers.append("validation_level_missing")
    if not deliverable.get("limitations"):
        blockers.append("limitations_missing")
    if not list_review_records(deliverable_id=deliverable_id):
        blockers.append("review_record_missing")
    capabilities = deliverable.get("capabilities", [])
    claim = (deliverable.get("provenance") or {}).get("delivery_claim", "")
    for capability in capabilities:
        status = get_product_feature_status(capability)
        if status.status == "planned" and claim == "production_model_result":
            blockers.append(f"planned_capability_cannot_claim_production:{capability}")
    warning_codes = {_warning_code(value) for value in deliverable.get("warnings", []) if _warning_code(value)}
    acknowledged = {row["warning_code"] for row in list_warning_acknowledgment_records(deliverable_id=deliverable_id)}
    missing_ack = sorted((warning_codes & CRITICAL_WARNINGS) - acknowledged)
    blockers.extend(f"warning_acknowledgment_missing:{code}" for code in missing_ack)
    if deliverable.get("scientific_validation_level") == "synthetic_demo":
        advisory.append("EXPERIMENTAL: real project independent validation is not complete")
    advisory.extend(sorted(warning_codes))
    return {
        "status": "blocked" if blockers else ("ready_with_warnings" if advisory else "ready"),
        "deliverable_id": deliverable_id,
        "scientific_validation_level": deliverable.get("scientific_validation_level"),
        "delivery_review_status": deliverable.get("review_status"),
        "blockers": blockers,
        "warnings": advisory,
        "required_actions": [item.replace("_", " ") for item in blockers],
    }


def transition_delivery(
    deliverable_id: str, action: str, *, actor: str, role: str, comment: str,
) -> dict[str, Any]:
    deliverable = get_deliverable_record(deliverable_id)
    if not deliverable:
        raise KeyError(deliverable_id)
    if role not in ROLE_ACTIONS or action not in ROLE_ACTIONS[role]:
        raise PermissionError(f"Role {role} cannot perform {action}")
    if not comment.strip():
        raise ValueError("Review action requires a comment")
    if action not in TRANSITIONS:
        raise ValueError(f"Unsupported review action: {action}")
    allowed, target = TRANSITIONS[action]
    current = deliverable["review_status"]
    if current not in allowed:
        raise ValueError(f"Invalid delivery transition: {current} -> {target}")
    if action == "approve":
        readiness = assess_delivery_readiness(deliverable_id)
        if readiness["status"] == "blocked":
            raise ValueError("Approval blocked: " + "; ".join(readiness["blockers"]))
    scientific_before = deliverable["scientific_validation_level"]
    review = create_review_record(
        review_id=f"rev_{uuid.uuid4().hex[:12]}", deliverable_id=deliverable_id,
        reviewer_name=actor, reviewer_role=role, action=action, comment=comment,
        software_user_reference="local_logic_role_only", validation_snapshot={"scientific_validation_level": scientific_before},
        warnings_snapshot=deliverable.get("warnings", []),
    )
    updated = update_deliverable_record(deliverable_id, review_status=target)
    if updated.get("scientific_validation_level") != scientific_before:
        raise RuntimeError("Delivery review attempted to alter scientific validation")
    if action == "approve":
        freeze_artifacts(list(dict.fromkeys([*updated.get("artifact_ids", []), *updated.get("report_ids", [])])))
    write_deliverable_manifest(deliverable_id, force=action == "approve")
    updated = get_deliverable_record(deliverable_id) or updated
    if action == "approve":
        for report_id in updated.get("report_ids", []):
            write_report_delivery_metadata(report_id, deliverable_id)
    audit_action = {"submit": "submitted", "review": "reviewed", "request_changes": "changes_requested", "approve": "approved"}.get(action, action)
    _audit(updated, actor, audit_action, f"Delivery review action: {action}.", {"review_id": review["review_id"]})
    return updated


def submit_delivery(deliverable_id: str, *, actor: str = "analyst", comment: str = "Submitted for technical review.") -> dict[str, Any]:
    return transition_delivery(deliverable_id, "submit", actor=actor, role="analyst", comment=comment)


def review_delivery(deliverable_id: str, *, actor: str = "technical_reviewer", comment: str = "Technical review completed.") -> dict[str, Any]:
    return transition_delivery(deliverable_id, "review", actor=actor, role="technical_reviewer", comment=comment)


def request_delivery_changes(deliverable_id: str, *, actor: str = "technical_reviewer", comment: str) -> dict[str, Any]:
    return transition_delivery(deliverable_id, "request_changes", actor=actor, role="technical_reviewer", comment=comment)


def approve_delivery(deliverable_id: str, *, actor: str = "project_manager", comment: str = "Approved for delivery.") -> dict[str, Any]:
    return transition_delivery(deliverable_id, "approve", actor=actor, role="project_manager", comment=comment)


def reject_delivery(deliverable_id: str, *, actor: str = "project_manager", comment: str) -> dict[str, Any]:
    return transition_delivery(deliverable_id, "reject", actor=actor, role="project_manager", comment=comment)


def supersede_delivery(deliverable_id: str, *, actor: str = "project_manager", comment: str) -> dict[str, Any]:
    return transition_delivery(deliverable_id, "supersede", actor=actor, role="project_manager", comment=comment)


def delivery_status(deliverable_id: str) -> dict[str, Any]:
    deliverable = get_deliverable_record(deliverable_id)
    if not deliverable:
        raise KeyError(deliverable_id)
    return {
        "deliverable": deliverable,
        "readiness": assess_delivery_readiness(deliverable_id),
        "reviews": list_review_records(deliverable_id=deliverable_id),
        "warning_acknowledgments": list_warning_acknowledgment_records(deliverable_id=deliverable_id),
        "integrity": verify_deliverable(deliverable_id),
    }


def write_delivery_governance_outputs(deliverable_id: str, output_dir: str | Path) -> dict[str, Any]:
    import json
    import pandas as pd
    from hydrolite.runtime_db import (
        get_configuration_snapshot_record, get_data_snapshot_record, get_project_version_record,
        list_audit_event_records,
    )

    deliverable = get_deliverable_record(deliverable_id)
    if not deliverable:
        raise KeyError(deliverable_id)
    version = get_project_version_record(deliverable["project_version_id"]) or {}
    data = get_data_snapshot_record(version.get("data_snapshot_id")) or {}
    config = get_configuration_snapshot_record(version.get("configuration_snapshot_id")) or {}
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    paths = write_deliverable_manifest(deliverable_id, output)
    payloads = {
        "project_version_manifest.json": version,
        "data_snapshot_manifest.json": data,
        "configuration_snapshot.json": config,
        "delivery_readiness.json": assess_delivery_readiness(deliverable_id),
        "integrity_verification.json": verify_deliverable(deliverable_id),
    }
    for name, payload in payloads.items():
        (output / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    reviews_path = output / "review_history.xlsx"
    audit_path = output / "audit_log.xlsx"
    pd.DataFrame(list_review_records(deliverable_id=deliverable_id)).to_excel(reviews_path, index=False)
    pd.DataFrame(list_audit_event_records(deliverable_id=deliverable_id)).to_excel(audit_path, index=False)
    return {**paths, "review_history": reviews_path, "audit_log": audit_path, **{name: output / name for name in payloads}}


def run_delivery_governance_demo(
    project: str | Path, output_dir: str | Path, *, project_version_id: str | None = None,
) -> dict[str, Any]:
    """Govern existing lightweight outputs without rerunning any scientific model."""
    from hydrolite.artifact_store import register_artifact
    from hydrolite.deliverable_package import create_delivery_bundle, create_project_package
    from hydrolite.integrity_verification import verify_artifact, verify_project_package
    from hydrolite.project_versioning import capture_delivery_environment, create_project_version, resolve_project
    from hydrolite.runtime_db import create_run_record, update_deliverable_record

    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    project_record = resolve_project(project)
    version = get_project_version_record(project_version_id) if project_version_id else create_project_version(project, created_by="delivery_demo", description="Existing-results governance demo")
    if not version or version["project_id"] != project_record["project_id"]:
        raise ValueError("Demo project version is missing or belongs to another project")
    environment = capture_delivery_environment(version["project_version_id"])
    run_id = f"run_delivery_demo_{uuid.uuid4().hex[:8]}"
    create_run_record(
        run_id=run_id, project_id=project_record["project_id"], project_version_id=version["project_version_id"],
        data_snapshot_id=version["data_snapshot_id"], configuration_snapshot_id=version["configuration_snapshot_id"],
        workflow_id="delivery_governance_demo", run_name="Existing results delivery demo", run_mode="existing_results_snapshot",
        status="succeeded", result_status="existing_artifacts_linked", legacy_unversioned=False,
        git_commit=version["git_commit"], hydrolite_version=version["software_version"],
        python_version="sanitized_in_environment_snapshot", environment_id=environment["environment_id"],
        warnings=["DEMO_EXISTING_RESULTS_ONLY"],
    )
    workspace = Path(project_record["workspace_path"])
    report_path = workspace / "reports" / "project_report.md"
    artifact_path = workspace / "output" / "batch_summary.xlsx"
    if not report_path.is_file() or not artifact_path.is_file():
        raise FileNotFoundError("Delivery demo requires existing project_report.md and batch_summary.xlsx")
    artifact = register_artifact(run_id, None, artifact_path)
    report = register_artifact(run_id, None, report_path)
    deliverable = create_deliverable(
        version["project_version_id"], run_ids=[run_id], artifact_ids=[artifact["artifact_id"]],
        report_ids=[report["artifact_id"]], created_by="delivery_demo", scientific_validation_level="framework_ready",
        capabilities=["hydrology"], warnings=["GEE_COMPUTE_AUTH_UNAVAILABLE"],
        limitations=["This demo governs existing outputs and does not rerun or independently validate the scientific model."],
    )
    delivery_id = deliverable["deliverable_id"]
    submit_delivery(delivery_id, actor="demo_analyst", comment="Submit existing-results governance demo.")
    review_delivery(delivery_id, actor="demo_reviewer", comment="Technical structure and limitations reviewed.")
    acknowledge_warning(delivery_id, "GEE_COMPUTE_AUTH_UNAVAILABLE", actor="demo_reviewer", comment="Acknowledged; offline outputs remain reviewable.")
    approve_delivery(delivery_id, actor="demo_manager", comment="Approved for delivery governance demonstration only.")
    governance_outputs = write_delivery_governance_outputs(delivery_id, output)
    delivery_bundle = create_delivery_bundle(delivery_id, output / "delivery_bundle.zip")
    thin_package = create_project_package(project, output / "thin_project.zip", mode="thin")
    portable_package = create_project_package(
        project, output / "portable_project.zip", mode="portable",
        selected_artifact_ids=[artifact["artifact_id"], report["artifact_id"]],
    )
    tampered_copy = output / "tampered_artifact_copy.xlsx"
    tampered_copy.write_bytes(artifact_path.read_bytes() + b"tampered-copy")
    tamper_result = verify_artifact(artifact["artifact_id"], tampered_copy)

    blocked = create_deliverable(
        version["project_version_id"], run_ids=[run_id], artifact_ids=[artifact["artifact_id"]],
        report_ids=[], limitations=["Missing report demo."], scientific_validation_level="framework_ready",
    )
    submit_delivery(blocked["deliverable_id"], comment="Submit blocked demo.")
    review_delivery(blocked["deliverable_id"], comment="Review blocked demo.")
    blocked_readiness = assess_delivery_readiness(blocked["deliverable_id"])

    experimental = create_deliverable(
        version["project_version_id"], run_ids=[run_id], artifact_ids=[artifact["artifact_id"]], report_ids=[report["artifact_id"]],
        scientific_validation_level="synthetic_demo", capabilities=["flood_susceptibility", "flood_susceptibility_xai"],
        limitations=["Synthetic method demo; not real-world risk evidence."],
    )
    submit_delivery(experimental["deliverable_id"], comment="Submit experimental delivery.")
    review_delivery(experimental["deliverable_id"], comment="Review experimental limitations.")
    for code in ("REAL_DATA_VALIDATION_MISSING", "XAI_IMPORTANCE_UNSTABLE"):
        acknowledge_warning(experimental["deliverable_id"], code, actor="demo_reviewer", comment="Acknowledged; scientific status remains experimental.")
    experimental_approved = approve_delivery(experimental["deliverable_id"], comment="Approved as explicitly experimental evidence.")

    planned = create_deliverable(
        version["project_version_id"], run_ids=[run_id], artifact_ids=[artifact["artifact_id"]], report_ids=[report["artifact_id"]],
        scientific_validation_level="framework_ready", capabilities=["water_quality"], delivery_claim="production_model_result",
        limitations=["Water quality production model is planned and not implemented."],
    )
    submit_delivery(planned["deliverable_id"], comment="Submit planned-capability negative test.")
    review_delivery(planned["deliverable_id"], comment="Review planned-capability negative test.")
    planned_readiness = assess_delivery_readiness(planned["deliverable_id"])
    demo_summary = {
        "status": "passed",
        "project_version_id": version["project_version_id"],
        "run_id": run_id,
        "deliverable_id": delivery_id,
        "review_status": get_deliverable_record(delivery_id)["review_status"],
        "scientific_validation_level": get_deliverable_record(delivery_id)["scientific_validation_level"],
        "blocked_approval": blocked_readiness,
        "experimental_delivery": {"review_status": experimental_approved["review_status"], "scientific_validation_level": experimental_approved["scientific_validation_level"]},
        "planned_water_quality": planned_readiness,
        "tampered_copy_verification": tamper_result,
        "packages": {
            "delivery": str(delivery_bundle), "thin": str(thin_package), "portable": str(portable_package),
            "thin_verification": verify_project_package(thin_package), "portable_verification": verify_project_package(portable_package),
        },
        "outputs": {key: str(value) for key, value in governance_outputs.items()},
        "models_rerun": False,
    }
    (output / "delivery_demo_summary.json").write_text(json.dumps(demo_summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return demo_summary
