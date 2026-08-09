from __future__ import annotations

from pathlib import Path

import yaml

from tests.runtime_helpers import configure_runtime


def make_delivery_workspace(monkeypatch, tmp_path: Path, project_id: str = "delivery_demo") -> Path:
    configure_runtime(monkeypatch, tmp_path)
    workspace = tmp_path / project_id
    (workspace / "cases").mkdir(parents=True)
    (workspace / "data").mkdir()
    (workspace / "data" / "rain.csv").write_text(
        "datetime,subbasin_id,rain_mm\n2026-01-01T00:00:00,S1,2\n2026-01-01T01:00:00,S1,3\n",
        encoding="utf-8",
    )
    (workspace / "project.yaml").write_text(
        yaml.safe_dump({"project_id": project_id, "project_name": "Delivery Demo", "modules": {"hydrolite": True}}, sort_keys=False),
        encoding="utf-8",
    )
    (workspace / "cases" / "demo.yaml").write_text(
        yaml.safe_dump({
            "case_name": "demo",
            "input": {"rainfall_csv": "data/rain.csv"},
            "hydrology": {"method": "scs_cn", "cn": 75},
            "routing": {"channel_method": "muskingum", "k_hours": 1.0, "x": 0.2},
        }, sort_keys=False),
        encoding="utf-8",
    )
    return workspace


def seed_governed_delivery(
    monkeypatch, tmp_path: Path, *, warning: str | None = None,
    validation: str = "framework_ready", capabilities: tuple[str, ...] = (), claim: str = "analysis_report",
):
    workspace = make_delivery_workspace(monkeypatch, tmp_path)
    from hydrolite.artifact_store import register_artifact
    from hydrolite.delivery_review import create_deliverable
    from hydrolite.project_versioning import create_project_version
    from hydrolite.runtime_db import create_run_record
    from hydrolite.runtime_paths import ensure_runtime_directories

    version = create_project_version(workspace, scenario_ids=["demo"])
    run_id = "run_delivery_demo"
    create_run_record(
        run_id=run_id,
        project_id=version["project_id"],
        project_version_id=version["project_version_id"],
        data_snapshot_id=version["data_snapshot_id"],
        configuration_snapshot_id=version["configuration_snapshot_id"],
        workflow_id="watershed_hydrology",
        status="succeeded",
        result_status="success",
        legacy_unversioned=False,
        git_commit=version["git_commit"],
        hydrolite_version=version["software_version"],
        warnings=[],
    )
    paths = ensure_runtime_directories(run_id)
    result_path = paths["artifacts"] / "result_v1.csv"
    report_path = paths["reports"] / "report_v1.md"
    result_path.write_text("datetime,flow\n2026-01-01T00:00:00,1.2\n", encoding="utf-8")
    report_path.write_text("# Delivery report\n\nScientific limitations are retained.\n", encoding="utf-8")
    artifact = register_artifact(run_id, None, result_path)
    report = register_artifact(run_id, None, report_path)
    deliverable = create_deliverable(
        version["project_version_id"],
        run_ids=[run_id],
        artifact_ids=[artifact["artifact_id"]],
        report_ids=[report["artifact_id"]],
        scientific_validation_level=validation,
        capabilities=capabilities,
        warnings=[warning] if warning else [],
        limitations=["Project-specific validation remains the client's responsibility."],
        delivery_claim=claim,
    )
    return {
        "workspace": workspace,
        "version": version,
        "run_id": run_id,
        "artifact": artifact,
        "report": report,
        "deliverable": deliverable,
    }
