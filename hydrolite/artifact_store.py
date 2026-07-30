from __future__ import annotations

from pathlib import Path
import hashlib
import json
import mimetypes
import shutil
import uuid
import zipfile

import pandas as pd

from hydrolite.runtime_db import (
    create_artifact_record,
    get_run_record,
    list_artifact_records,
    update_artifact_record,
)
from hydrolite.runtime_paths import get_run_dir


FORBIDDEN_PARTS = {"temp", "cache", "raw", "uploads", "external", ".git", ".streamlit"}
FORBIDDEN_SUFFIXES = {".sqlite3", ".dss", ".h5", ".hdf5", ".nc", ".pt", ".pth", ".ckpt", ".onnx", ".key", ".pem"}


def calculate_artifact_checksum(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_artifact(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".csv": "table", ".xlsx": "table", ".json": "manifest", ".yaml": "configuration", ".yml": "configuration",
        ".md": "report", ".png": "chart", ".jpg": "chart", ".jpeg": "chart", ".geojson": "vector",
        ".tif": "raster", ".tiff": "raster", ".asc": "raster", ".zip": "archive", ".log": "log",
    }.get(suffix, "unknown")


def register_artifact(run_id: str, task_id: str | None, path: str | Path) -> dict:
    source = Path(path).resolve()
    if not source.is_file(): raise FileNotFoundError(source)
    run = get_run_record(run_id)
    if not run: raise KeyError(run_id)
    checksum = calculate_artifact_checksum(source)
    existing = [row for row in list_artifact_records(run_id=run_id) if row.get("path") == str(source)]
    if existing:
        return update_artifact_record(
            existing[0]["artifact_id"],
            size=source.stat().st_size,
            checksum=checksum,
            quality_status="unchecked",
        )
    kind = classify_artifact(source)
    artifact_id = f"art_{uuid.uuid4().hex[:12]}"
    try: relative = str(source.relative_to(get_run_dir(run_id)))
    except ValueError: relative = source.name
    return create_artifact_record(
        artifact_id=artifact_id, run_id=run_id, task_id=task_id, project_id=run["project_id"],
        artifact_type=kind, display_name=source.name, path=str(source), relative_path=relative,
        media_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream", size=source.stat().st_size,
        checksum=checksum, source_stage="", quality_status="unchecked",
        preview_available=kind in {"table", "manifest", "configuration", "report", "chart", "vector"},
        downloadable=True, lineage_dataset_id="", warnings=[],
    )


def discover_run_artifacts(run_id: str) -> list[dict]:
    root = get_run_dir(run_id)
    artifacts = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.endswith(".sqlite3"): continue
        relative = path.relative_to(root)
        if set(relative.parts) & {"temp", "cache"}: continue
        artifacts.append(register_artifact(run_id, None, path))
    build_artifact_index(run_id)
    return artifacts


def validate_artifact(path: str | Path, artifact_type: str) -> dict:
    from hydrolite.artifact_validation import (
        validate_raster_artifact, validate_report_artifact, validate_table_artifact, validate_vector_artifact,
    )
    if artifact_type in {"table", "timeseries"}: return validate_table_artifact(path)
    if artifact_type == "vector": return validate_vector_artifact(path)
    if artifact_type == "raster": return validate_raster_artifact(path)
    return validate_report_artifact(path)


def preview_artifact(path: str | Path) -> dict:
    source = Path(path); kind = classify_artifact(source)
    if source.stat().st_size > 20 * 1024 * 1024:
        return {"status": "metadata_only", "size": source.stat().st_size, "checksum": calculate_artifact_checksum(source)}
    if source.suffix.lower() == ".csv": return {"status": "passed", "data": pd.read_csv(source).head(20).to_dict("records")}
    if source.suffix.lower() == ".xlsx": return {"status": "passed", "data": pd.read_excel(source).head(20).to_dict("records")}
    if source.suffix.lower() in {".json", ".geojson", ".yaml", ".yml", ".md"}:
        return {"status": "passed", "text": source.read_text(encoding="utf-8", errors="replace")[:10000]}
    return {"status": "metadata_only", "type": kind, "size": source.stat().st_size}


def build_artifact_index(run_id: str) -> Path:
    path = get_run_dir(run_id) / "reports" / "run_artifact_index.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list_artifact_records(run_id=run_id)).to_excel(path, index=False)
    return path


def search_artifacts(project_id: str | None = None, run_id: str | None = None, query: str | None = None) -> list[dict]:
    rows = list_artifact_records(**{key: value for key, value in {"project_id": project_id, "run_id": run_id}.items() if value})
    if query:
        needle = query.casefold()
        rows = [row for row in rows if needle in f"{row['display_name']} {row['artifact_type']} {row['source_stage']}".casefold()]
    return rows


def copy_artifact_to_export(artifact_id: str, output_dir: str | Path) -> Path:
    rows = [row for row in list_artifact_records() if row["artifact_id"] == artifact_id]
    if not rows: raise KeyError(artifact_id)
    source = Path(rows[0]["path"]); target = Path(output_dir) / source.name
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    return target


def create_artifact_bundle(run_id: str, output_path: str | Path) -> Path:
    target = Path(output_path)
    if target.suffix.lower() != ".zip": target = target / f"{run_id}_artifacts.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    root = get_run_dir(run_id)
    added = set()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for artifact in list_artifact_records(run_id=run_id):
            path = Path(artifact["path"])
            if not path.exists() or path.suffix.lower() in FORBIDDEN_SUFFIXES: continue
            try: relative = path.resolve().relative_to(root)
            except ValueError: continue
            if set(relative.parts) & FORBIDDEN_PARTS: continue
            if any(word in relative.as_posix().lower() for word in ("credential", "secret", "token", "service-account")): continue
            if relative.as_posix() in added: continue
            archive.write(path, relative.as_posix())
            added.add(relative.as_posix())
        archive.writestr("bundle_manifest.json", json.dumps({"run_id": run_id, "artifact_count": len(list_artifact_records(run_id=run_id))}, indent=2))
    return target


def verify_artifact_bundle(bundle_path: str | Path) -> dict:
    errors = []
    with zipfile.ZipFile(bundle_path) as archive:
        for info in archive.infolist():
            path = Path(info.filename)
            if path.is_absolute() or ".." in path.parts: errors.append(f"unsafe path: {info.filename}")
            if path.suffix.lower() in FORBIDDEN_SUFFIXES or set(path.parts) & FORBIDDEN_PARTS: errors.append(f"forbidden member: {info.filename}")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def mark_artifact_superseded(artifact_id: str, replacement_id: str) -> dict:
    return update_artifact_record(artifact_id, quality_status="superseded", warnings=[f"Replaced by {replacement_id}"])
