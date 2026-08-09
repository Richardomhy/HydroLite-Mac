"""Safe delivery bundles and portable HydroLite project packages."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
import hashlib
import json
import re
import shutil
import stat
import uuid
import zipfile

from hydrolite.deliverable_manifest import sanitize_manifest_paths, write_deliverable_manifest
from hydrolite.integrity_verification import hash_file, verify_deliverable, verify_project_package
from hydrolite.project_versioning import create_project_version, list_project_versions, resolve_project
from hydrolite.runtime_db import (
    create_audit_event_record,
    get_artifact_record,
    get_configuration_snapshot_record,
    get_data_snapshot_record,
    get_deliverable_record,
    get_project_record,
    get_project_version_record,
    list_artifact_records,
    list_run_records,
    update_deliverable_record,
)
from hydrolite.runtime_paths import get_project_runtime_dir


PACKAGE_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = {1}
FORBIDDEN_PARTS = {
    ".git", ".streamlit", ".env", "external", "credentials", "credential", "secrets", "secret",
    "tokens", "token", "cache", "tmp", "logs", "data_raw",
}
FORBIDDEN_SUFFIXES = {
    ".sqlite", ".sqlite3", ".db", ".dss", ".h5", ".hdf5", ".nc", ".nc4",
    ".pt", ".pth", ".ckpt", ".onnx", ".pem", ".key", ".p12", ".pdf",
}
SENSITIVE_RULES = {
    "private_key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY", re.I),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    "credential_assignment": re.compile(r"(?i)\b(token|secret|password|api[_-]?key)\b\s*[:=]\s*[^\s]{6,}"),
    "service_account": re.compile(r'"type"\s*:\s*"service_account"', re.I),
}
TEXT_PACKAGE_SUFFIXES = {".csv", ".geojson", ".html", ".json", ".md", ".txt", ".xml", ".yaml", ".yml"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_member_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return not path.is_absolute() and ".." not in path.parts and not (set(part.casefold() for part in path.parts) & FORBIDDEN_PARTS)


def _forbidden_file(path: Path) -> str | None:
    lowered = {part.casefold() for part in path.parts}
    if lowered & FORBIDDEN_PARTS:
        return "forbidden_path"
    if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
        return "forbidden_file_type"
    if any(word in path.name.casefold() for word in ("credential", "secret", "private_key", "service-account")):
        return "sensitive_filename"
    return None


def scan_deliverable_for_sensitive_content(paths: Iterable[str | Path]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    for value in paths:
        path = Path(value)
        rule = _forbidden_file(path)
        if rule:
            findings.append({"file": path.name, "rule": rule, "status": "failed"})
            continue
        if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            continue
        for name, pattern in SENSITIVE_RULES.items():
            if pattern.search(text):
                findings.append({"file": path.name, "rule": name, "status": "failed"})
    return {"status": "passed" if not findings else "failed", "findings": findings}


def _archive_bytes(archive: zipfile.ZipFile, name: str, content: bytes, checksums: dict[str, str]) -> None:
    if not _safe_member_name(name):
        raise ValueError(f"Unsafe package member: {name}")
    archive.writestr(name, content)
    checksums[name] = hashlib.sha256(content).hexdigest()


def _packaged_file_bytes(source: Path, workspace: Path | None = None) -> bytes:
    content = source.read_bytes()
    if source.suffix.casefold() not in TEXT_PACKAGE_SUFFIXES:
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    replacements = [(str(Path.home()), "<HOME>")]
    if workspace:
        replacements.insert(0, (str(workspace.expanduser().resolve()), "project"))
    for absolute, logical in replacements:
        text = text.replace(absolute, logical)
    return text.encode("utf-8")


def _archive_file(
    archive: zipfile.ZipFile,
    name: str,
    source: Path,
    checksums: dict[str, str],
    *,
    workspace: Path | None = None,
) -> None:
    if _forbidden_file(source):
        raise ValueError(f"Forbidden package file: {source.name}")
    _archive_bytes(archive, name, _packaged_file_bytes(source, workspace), checksums)


def create_delivery_bundle(deliverable_id: str, output_path: str | Path | None = None) -> Path:
    deliverable = get_deliverable_record(deliverable_id)
    if not deliverable:
        raise KeyError(deliverable_id)
    if deliverable["review_status"] != "approved_for_delivery":
        raise ValueError("Delivery bundle requires approved_for_delivery status")
    integrity = verify_deliverable(deliverable_id)
    if integrity["status"] != "passed":
        raise ValueError("Deliverable integrity failed: " + "; ".join(integrity["errors"]))
    manifest_paths = write_deliverable_manifest(deliverable_id)
    artifacts = [get_artifact_record(item) for item in deliverable.get("artifact_ids", [])]
    reports = [get_artifact_record(item) for item in deliverable.get("report_ids", [])]
    records = [row for row in [*artifacts, *reports] if row]
    source_paths = [Path(row["path"]) for row in records]
    scan = scan_deliverable_for_sensitive_content(source_paths)
    if scan["status"] != "passed":
        raise ValueError("Sensitive content scan failed")
    version = get_project_version_record(deliverable["project_version_id"])
    project = get_project_record(deliverable["project_id"])
    project_name = str((project or {}).get("name") or deliverable["project_id"]).replace(" ", "_")
    version_number = (version or {}).get("version_number", "unknown")
    target = Path(output_path) if output_path else get_project_runtime_dir(deliverable["project_id"]) / "delivery" / f"{project_name}_{version_number}_delivery.zip"
    if target.suffix.lower() != ".zip":
        target = target / f"{project_name}_{version_number}_delivery.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}
    categories = {"report": "reports", "chart": "figures", "raster": "maps", "vector": "maps", "table": "tables", "timeseries": "tables"}
    used: set[str] = set()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        _archive_file(archive, "README_交付说明.md", manifest_paths["summary"], checksums)
        _archive_file(archive, "manifest.json", manifest_paths["manifest"], checksums)
        validation = json.dumps({
            "scientific_validation_level": deliverable["scientific_validation_level"],
            "delivery_review_status": deliverable["review_status"],
            "warnings": deliverable.get("warnings", []),
            "limitations": deliverable.get("limitations", []),
        }, indent=2, ensure_ascii=False).encode()
        _archive_bytes(archive, "validation_summary.json", validation, checksums)
        for row in records:
            source = Path(row["path"])
            category = categories.get(row.get("artifact_type"), "tables")
            name = f"{category}/{source.name}"
            if name in used:
                name = f"{category}/{row['artifact_id']}_{source.name}"
            _archive_file(archive, name, source, checksums, workspace=Path(project["workspace_path"]) if project else None)
            used.add(name)
        package_manifest = {
            "package_schema_version": PACKAGE_SCHEMA_VERSION,
            "package_type": "delivery_bundle",
            "project_id": deliverable["project_id"],
            "deliverable_id": deliverable_id,
            "mode": "frozen_delivery",
            "checksums": checksums,
            "generated_at": _now(),
        }
        archive.writestr("package_manifest.json", json.dumps(package_manifest, indent=2, ensure_ascii=False))
    package_hash = hash_file(target)
    update_deliverable_record(deliverable_id, package_hash=package_hash)
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=_now(), project_id=deliverable["project_id"],
        project_version_id=deliverable["project_version_id"], deliverable_id=deliverable_id,
        actor="local_user", action="package_exported", object_type="delivery_bundle", object_id=target.name,
        summary="Frozen delivery bundle exported.", metadata={"package_hash": package_hash},
    )
    return target


def create_project_package(
    project: str | Path, output_path: str | Path | None = None, *, mode: str = "thin",
    selected_data: Iterable[str | Path] = (), selected_artifact_ids: Iterable[str] = (),
) -> Path:
    if mode not in {"thin", "portable"}:
        raise ValueError("Project package mode must be thin or portable")
    project_record = resolve_project(project)
    workspace = Path(project_record["workspace_path"])
    versions = list_project_versions(project_record["project_id"])
    if not versions:
        create_project_version(
            workspace,
            created_by="project_export",
            description="Automatically frozen before project package export.",
        )
        versions = list_project_versions(project_record["project_id"])
    project_safe = sanitize_manifest_paths(project_record, workspace)
    artifact_records = [get_artifact_record(item) for item in selected_artifact_ids]
    artifact_records = [row for row in artifact_records if row]
    data_paths = [Path(value).expanduser().resolve() for value in selected_data]
    if mode == "thin" and data_paths:
        raise ValueError("Thin package cannot include selected data")
    for path in data_paths:
        if "data_raw" in {part.casefold() for part in path.parts}:
            raise ValueError("data_raw is never included in project packages")
        if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
            raise ValueError(f"Portable data must be an existing file no larger than 50 MB: {path.name}")
    sources = [*data_paths, *(Path(row["path"]) for row in artifact_records)]
    scan = scan_deliverable_for_sensitive_content(sources)
    if scan["status"] != "passed":
        raise ValueError("Sensitive content scan failed")
    default_name = f"{project_record['project_id']}_{mode}.hydrolite-project.zip"
    target = Path(output_path) if output_path else get_project_runtime_dir(project_record["project_id"]) / "delivery" / default_name
    if target.suffix.lower() != ".zip":
        target = target / default_name
    target.parent.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        _archive_bytes(archive, "project.json", json.dumps(project_safe, indent=2, ensure_ascii=False).encode(), checksums)
        project_yaml = workspace / "project.yaml"
        if project_yaml.exists():
            _archive_file(archive, "configs/project.yaml", project_yaml, checksums, workspace=workspace)
        for version in versions:
            version_id = version["project_version_id"]
            _archive_bytes(archive, f"versions/{version_id}.json", json.dumps(sanitize_manifest_paths(version, workspace), indent=2, ensure_ascii=False).encode(), checksums)
            data = get_data_snapshot_record(version["data_snapshot_id"])
            config = get_configuration_snapshot_record(version["configuration_snapshot_id"])
            if data:
                _archive_bytes(archive, f"versions/{version_id}_data.json", json.dumps(sanitize_manifest_paths(data, workspace), indent=2, ensure_ascii=False).encode(), checksums)
            if config:
                _archive_bytes(archive, f"configs/{version_id}.json", json.dumps(sanitize_manifest_paths(config, workspace), indent=2, ensure_ascii=False).encode(), checksums)
        _archive_bytes(
            archive,
            "manifests/project_versions.json",
            json.dumps([sanitize_manifest_paths(row, workspace) for row in versions], indent=2, ensure_ascii=False).encode(),
            checksums,
        )
        runs = [row for row in list_run_records(project_id=project_record["project_id"]) if row.get("project_version_id")]
        _archive_bytes(archive, "runs/run_metadata.json", json.dumps(sanitize_manifest_paths(runs, workspace), indent=2, ensure_ascii=False).encode(), checksums)
        artifact_metadata = [sanitize_manifest_paths(row, workspace) for row in list_artifact_records(project_id=project_record["project_id"])]
        _archive_bytes(archive, "artifacts/artifact_metadata.json", json.dumps(artifact_metadata, indent=2, ensure_ascii=False).encode(), checksums)
        if mode == "portable":
            for index, path in enumerate(data_paths, 1):
                _archive_file(archive, f"data/{index:03d}_{path.name}", path, checksums, workspace=workspace)
            for row in artifact_records:
                _archive_file(
                    archive,
                    f"artifacts/files/{row['artifact_id']}_{Path(row['path']).name}",
                    Path(row["path"]),
                    checksums,
                    workspace=workspace,
                )
        manifest = {
            "package_schema_version": PACKAGE_SCHEMA_VERSION,
            "package_type": "hydrolite_project",
            "project_id": project_record["project_id"],
            "mode": mode,
            "version_ids": [row["project_version_id"] for row in versions],
            "checksums": checksums,
            "generated_at": _now(),
            "absolute_paths_sanitized": True,
        }
        archive.writestr("package_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    result = verify_project_package(target)
    if result["status"] != "passed":
        target.unlink(missing_ok=True)
        raise ValueError("Generated project package failed verification: " + "; ".join(result["errors"]))
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=_now(), project_id=project_record["project_id"],
        project_version_id=versions[-1]["project_version_id"], deliverable_id="", actor="local_user",
        action="package_verified", object_type="project_package", object_id=target.name,
        summary="Generated project package passed verification.", metadata={"package_schema_version": PACKAGE_SCHEMA_VERSION},
    )
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=_now(), project_id=project_record["project_id"],
        project_version_id=versions[-1]["project_version_id"], deliverable_id="", actor="local_user",
        action="package_exported", object_type="project_package", object_id=target.name,
        summary=f"{mode} project package exported.", metadata={"package_hash": hash_file(target)},
    )
    return target


def import_project_package(
    package: str | Path, target_root: str | Path, *, conflict_mode: str = "import_as_copy",
) -> dict[str, Any]:
    verification = verify_project_package(package)
    if verification["status"] != "passed":
        raise ValueError("Package verification failed: " + "; ".join(verification["errors"]))
    if conflict_mode not in {"import_as_copy", "block_with_conflict"}:
        raise ValueError("Unknown conflict mode")
    source_project_id = str(verification.get("project_id") or "imported_project")
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=_now(), project_id=source_project_id,
        project_version_id="", deliverable_id="", actor="local_user", action="package_verified",
        object_type="project_package", object_id=Path(package).name, summary="Package passed pre-import verification.", metadata={},
    )
    existing = get_project_record(source_project_id)
    if existing and conflict_mode == "block_with_conflict":
        raise FileExistsError(f"Project ID conflict: {source_project_id}")
    imported_id = f"{source_project_id}_copy_{uuid.uuid4().hex[:6]}" if existing else source_project_id
    destination = Path(target_root).expanduser().resolve() / imported_id
    if destination.exists():
        raise FileExistsError(f"Import destination already exists: {destination.name}")
    destination.mkdir(parents=True)
    with zipfile.ZipFile(package) as archive:
        for info in archive.infolist():
            mode = info.external_attr >> 16
            path = PurePosixPath(info.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(mode):
                shutil.rmtree(destination, ignore_errors=True)
                raise ValueError(f"Unsafe package member: {info.filename}")
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not info.is_dir():
                target.write_bytes(archive.read(info))
    config = destination / "configs" / "project.yaml"
    if config.exists():
        root_config = destination / "project.yaml"
        text = config.read_text(encoding="utf-8")
        text = re.sub(r"(?m)^project_id:\s*.*$", f"project_id: {imported_id}", text)
        root_config.write_text(text, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "project_id": imported_id,
        "imported_from_project_id": source_project_id,
        "package_schema_version": verification["package_schema_version"],
        "datasets": [],
    }
    (destination / "workspace_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    create_audit_event_record(
        event_id=f"evt_{uuid.uuid4().hex[:12]}", timestamp=_now(), project_id=imported_id,
        project_version_id="", deliverable_id="", actor="local_user", action="package_imported",
        object_type="project_package", object_id=Path(package).name, summary="Verified project package imported.",
        metadata={"source_project_id": source_project_id, "conflict_mode": conflict_mode},
    )
    return {
        "status": "imported",
        "project_id": imported_id,
        "source_project_id": source_project_id,
        "project_dir": str(destination),
        "conflict_handling": "copied" if imported_id != source_project_id else "none",
        "verification": verification,
    }
