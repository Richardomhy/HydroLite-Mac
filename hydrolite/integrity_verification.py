"""SHA-256 verification for frozen artifacts, deliverables, and portable packages."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import stat
import zipfile

from hydrolite.runtime_db import get_artifact_record, get_deliverable_record


SUPPORTED_PACKAGE_SCHEMA_VERSIONS = {1}
FORBIDDEN_PACKAGE_PARTS = {"data_raw", "external", ".git", ".streamlit", ".env", "secrets", "credentials", "logs", "cache"}
FORBIDDEN_PACKAGE_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".dss", ".h5", ".hdf5", ".nc", ".nc4", ".pt", ".pth", ".ckpt", ".onnx", ".pem", ".key", ".p12"}
SENSITIVE_TEXT_MARKERS = ("BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY", '"type": "service_account"', "sk-")


def hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_manifest(manifest: str | Path | dict[str, Any]) -> str:
    payload = json.loads(Path(manifest).read_text(encoding="utf-8")) if not isinstance(manifest, dict) else dict(manifest)
    payload.pop("manifest_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_artifact(artifact: str | dict[str, Any], candidate_path: str | Path | None = None) -> dict[str, Any]:
    record = get_artifact_record(artifact) if isinstance(artifact, str) else artifact
    if not record:
        return {"status": "failed", "artifact_id": str(artifact), "errors": ["artifact_record_missing"]}
    path = Path(candidate_path) if candidate_path is not None else Path(str(record.get("path") or ""))
    if not path.is_file():
        return {"status": "failed", "artifact_id": record.get("artifact_id"), "errors": ["artifact_file_missing"]}
    actual = hash_file(path)
    expected = str(record.get("checksum") or "")
    return {
        "status": "passed" if expected and actual == expected else "failed",
        "artifact_id": record.get("artifact_id"),
        "candidate": path.name,
        "expected_checksum": expected,
        "actual_checksum": actual,
        "errors": [] if expected and actual == expected else ["artifact_checksum_mismatch"],
    }


def verify_report(report: str | dict[str, Any]) -> dict[str, Any]:
    result = verify_artifact(report)
    result["object_type"] = "report"
    return result


def verify_deliverable(deliverable: str | dict[str, Any]) -> dict[str, Any]:
    record = get_deliverable_record(deliverable) if isinstance(deliverable, str) else deliverable
    if not record:
        return {"status": "failed", "errors": ["deliverable_record_missing"], "artifacts": []}
    manifest_path = Path(str(record.get("manifest_path") or ""))
    errors: list[str] = []
    if not manifest_path.is_file():
        errors.append("deliverable_manifest_missing")
    elif hash_manifest(manifest_path) != str(record.get("manifest_hash") or ""):
        errors.append("deliverable_manifest_checksum_mismatch")
    artifact_results = [verify_artifact(artifact_id) for artifact_id in record.get("artifact_ids", [])]
    report_results = [verify_report(artifact_id) for artifact_id in record.get("report_ids", [])]
    if any(item["status"] != "passed" for item in [*artifact_results, *report_results]):
        errors.append("frozen_artifact_integrity_failed")
    return {
        "status": "passed" if not errors else "failed",
        "deliverable_id": record.get("deliverable_id"),
        "manifest_hash": record.get("manifest_hash"),
        "artifacts": artifact_results,
        "reports": report_results,
        "errors": errors,
    }


def _unsafe_member(info: zipfile.ZipInfo) -> str | None:
    name = info.filename.replace("\\", "/")
    path = PurePosixPath(name)
    if path.is_absolute() or name.startswith(("/", "\\")) or (len(name) > 2 and name[1:3] in {":/", ":\\"}):
        return "absolute_path"
    if ".." in path.parts:
        return "path_traversal"
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        return "symlink"
    if {part.casefold() for part in path.parts} & FORBIDDEN_PACKAGE_PARTS:
        return "forbidden_member"
    if path.suffix.casefold() in FORBIDDEN_PACKAGE_SUFFIXES:
        return "forbidden_member"
    if any(word in path.name.casefold() for word in ("credential", "private_key", "service-account")):
        return "sensitive_filename"
    return None


def verify_project_package(package: str | Path) -> dict[str, Any]:
    source = Path(package)
    errors: list[str] = []
    member_status: list[dict[str, str]] = []
    if not source.is_file() or not zipfile.is_zipfile(source):
        return {"status": "failed", "errors": ["invalid_zip"], "members": []}
    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        if len(names) != len(archive.namelist()):
            errors.append("duplicate_package_member")
        for info in archive.infolist():
            rule = _unsafe_member(info)
            member_status.append({"file": info.filename, "rule": rule or "safe", "status": "failed" if rule else "passed"})
            if rule:
                errors.append(f"{rule}:{info.filename}")
            elif not info.is_dir() and info.file_size <= 10 * 1024 * 1024:
                try:
                    text = archive.read(info).decode("utf-8")
                except (UnicodeDecodeError, RuntimeError):
                    text = ""
                if any(marker in text for marker in SENSITIVE_TEXT_MARKERS):
                    errors.append(f"sensitive_content:{info.filename}")
        if "package_manifest.json" not in names:
            errors.append("package_manifest_missing")
            manifest = {}
        else:
            try:
                manifest = json.loads(archive.read("package_manifest.json"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                manifest = {}
                errors.append("package_manifest_invalid")
        schema = manifest.get("package_schema_version")
        if schema not in SUPPORTED_PACKAGE_SCHEMA_VERSIONS:
            errors.append(f"unsupported_schema_version:{schema}")
        checksums = manifest.get("checksums", {}) if isinstance(manifest, dict) else {}
        version_ids = manifest.get("version_ids", []) if isinstance(manifest, dict) else []
        if len(version_ids) != len(set(version_ids)):
            errors.append("duplicate_version_id")
        if not isinstance(checksums, dict):
            errors.append("package_checksums_invalid")
            checksums = {}
        for name, expected in checksums.items():
            if name not in names:
                errors.append(f"package_member_missing:{name}")
                continue
            actual = hashlib.sha256(archive.read(name)).hexdigest()
            if actual != expected:
                errors.append(f"package_checksum_mismatch:{name}")
    return {
        "status": "passed" if not errors else "failed",
        "package": str(source),
        "package_schema_version": manifest.get("package_schema_version") if isinstance(manifest, dict) else None,
        "project_id": manifest.get("project_id") if isinstance(manifest, dict) else None,
        "mode": manifest.get("mode") if isinstance(manifest, dict) else None,
        "errors": errors,
        "members": member_status,
    }
