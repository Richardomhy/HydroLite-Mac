from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from hashlib import sha256
import csv
import json
import mimetypes
import re
import shutil
import stat
import zipfile
from typing import Any

import pandas as pd

from hydrolite.workspace import calculate_file_checksum, read_workspace_manifest, write_workspace_manifest


FORMAT_BY_SUFFIX = {
    ".csv": "csv", ".tsv": "tsv", ".xlsx": "xlsx", ".json": "json", ".yaml": "yaml",
    ".yml": "yaml", ".geojson": "geojson", ".gpkg": "gpkg", ".kml": "kml", ".kmz": "kmz",
    ".tif": "geotiff", ".tiff": "geotiff", ".asc": "ascii_grid", ".nc": "netcdf",
    ".h5": "hdf5", ".hdf5": "hdf5", ".inp": "swmm_inp", ".dss": "hec_dss",
    ".hms": "hec_hms_project", ".zip": "zip",
}


def calculate_upload_checksum(path: str | Path) -> str:
    return calculate_file_checksum(path)


def sanitize_uploaded_filename(filename: str) -> str:
    name = Path(filename).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not safe or safe.count(".") > 2 or any(part.lower() in {"exe", "app", "sh", "command", "dmg", "pkg"} for part in safe.split(".")[1:]):
        raise ValueError(f"Unsafe upload filename: {filename}")
    return safe


def detect_file_encoding(path: str | Path) -> dict[str, Any]:
    data = Path(path).read_bytes()[:65536]
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        return {"encoding": best.encoding if best else "utf-8", "confidence": float(1 - best.percent_chaos / 100) if best else 0.0}
    except Exception:
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                data.decode(encoding)
                return {"encoding": encoding, "confidence": 0.5}
            except UnicodeDecodeError:
                pass
        return {"encoding": "binary", "confidence": 0.0}


def _zip_members(path: Path) -> dict[str, Any]:
    required = {".shp", ".shx", ".dbf", ".prj"}
    found: set[str] = set()
    total = 0
    errors: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts:
                errors.append(f"Unsafe archive path: {info.filename}")
            if info.external_attr >> 16 & stat.S_IFLNK:
                errors.append(f"Symbolic link is not allowed: {info.filename}")
            total += info.file_size
            found.add(Path(info.filename).suffix.lower())
        if len(archive.infolist()) > 1000 or total > 500 * 1024 * 1024 or total > max(path.stat().st_size * 200, 100 * 1024 * 1024):
            errors.append("Archive expansion limits exceeded.")
    missing = sorted(required - found) if ".shp" in found else []
    return {"status": "passed" if not errors and not missing else ("crs_missing" if missing == [".prj"] else "failed"), "errors": errors, "missing_shapefile_parts": missing, "uncompressed_size": total, "shapefile": ".shp" in found}


def detect_file_format(path: str | Path) -> str:
    target = Path(path)
    fmt = FORMAT_BY_SUFFIX.get(target.suffix.lower(), "unsupported")
    if fmt == "zip":
        info = _zip_members(target)
        return "zip_shapefile" if info["shapefile"] else "zip"
    if fmt == "json":
        try:
            content = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(content, dict) and content.get("type") in {"FeatureCollection", "Feature"}:
                return "geojson"
        except Exception:
            pass
    return fmt


def detect_table_structure(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    fmt = detect_file_format(target)
    if fmt in {"csv", "tsv"}:
        encoding = detect_file_encoding(target)["encoding"]
        separator = "\t" if fmt == "tsv" else ","
        frame = pd.read_csv(target, sep=separator, encoding=encoding)
        return {"status": "passed", "sheets": [], "selected_sheet": None, "columns": list(frame.columns), "rows": len(frame), "preview": frame.head(20)}
    if fmt == "xlsx":
        book = pd.ExcelFile(target)
        previews = {sheet: pd.read_excel(target, sheet_name=sheet, nrows=20) for sheet in book.sheet_names}
        return {"status": "needs_sheet_selection", "sheets": book.sheet_names, "selected_sheet": None, "columns": [], "rows": None, "sheet_previews": previews}
    if fmt in {"json", "geojson"}:
        content = json.loads(target.read_text(encoding="utf-8"))
        rows = content.get("features", []) if fmt == "geojson" else content
        frame = pd.json_normalize(rows)
        return {"status": "passed", "sheets": [], "selected_sheet": None, "columns": list(frame.columns), "rows": len(frame), "preview": frame.head(20)}
    return {"status": "unsupported_format", "columns": [], "rows": None}


def detect_vector_structure(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    fmt = detect_file_format(target)
    if fmt == "geojson":
        data = json.loads(target.read_text(encoding="utf-8"))
        features = data.get("features", [])
        types = sorted({(feature.get("geometry") or {}).get("type", "null") for feature in features})
        crs = (data.get("crs") or {}).get("properties", {}).get("name", "EPSG:4326")
        return {"status": "passed", "feature_count": len(features), "geometry_types": types, "crs": crs}
    if fmt == "zip_shapefile":
        return _zip_members(target)
    return {"status": "optional_backend_required", "format": fmt}


def detect_raster_structure(path: str | Path) -> dict[str, Any]:
    from hydrolite.raster_ingestion import inspect_raster
    return inspect_raster(path)


def detect_timeseries_structure(path: str | Path) -> dict[str, Any]:
    from hydrolite.timeseries_ingestion import detect_timestamp_column, infer_time_interval
    structure = detect_table_structure(path)
    frame = structure.get("preview")
    if not isinstance(frame, pd.DataFrame):
        return {"status": structure["status"], "timestamp_column": None}
    column = detect_timestamp_column(frame)
    return {"status": "passed" if column else "timestamp_missing", "timestamp_column": column, "interval": infer_time_interval(frame, column) if column else {}}


def reject_unsafe_archive(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not zipfile.is_zipfile(target):
        return {"status": "failed", "errors": ["Not a ZIP archive."]}
    return _zip_members(target)


def extract_safe_archive(path: str | Path, output_dir: str | Path) -> list[Path]:
    check = reject_unsafe_archive(path)
    if check["status"] == "failed":
        raise ValueError("; ".join(check["errors"]))
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            target = (output / info.filename).resolve()
            if output not in target.parents and target != output:
                raise ValueError(f"Unsafe archive path: {info.filename}")
            if not info.is_dir():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                extracted.append(target)
    return extracted


def preview_uploaded_dataset(path: str | Path, max_rows: int = 20) -> dict[str, Any]:
    structure = detect_table_structure(path)
    frame = structure.get("preview")
    return {**{key: value for key, value in structure.items() if key not in {"preview", "sheet_previews"}}, "preview": frame.head(max_rows).to_dict("records") if isinstance(frame, pd.DataFrame) else []}


def classify_uploaded_dataset(path: str | Path, hints: dict[str, Any] | None = None) -> dict[str, Any]:
    fmt = detect_file_format(path)
    declared = (hints or {}).get("dataset_type")
    if declared:
        return {"dataset_type": declared, "confidence": 1.0, "reason": "user_declared"}
    if fmt in {"geojson", "zip_shapefile", "gpkg", "kml", "kmz"}:
        return {"dataset_type": "watershed_boundary", "confidence": 0.6, "reason": "vector format requires user confirmation"}
    structure = detect_table_structure(path)
    columns = {str(name).lower() for name in structure.get("columns", [])}
    rules = [
        ("rainfall_observed", {"timestamp", "rainfall_mm"}),
        ("streamflow_observed", {"timestamp", "flow_cms"}),
        ("subbasins", {"subbasin_id", "area_km2"}),
        ("reaches", {"reach_id"}),
        ("stage_area_volume", {"stage_m", "volume_m3"}),
        ("water_quality_observations", {"station_id", "concentration_mg_l"}),
    ]
    for dataset_type, required in rules:
        if required <= columns:
            return {"dataset_type": dataset_type, "confidence": 0.95, "reason": f"matched fields: {', '.join(sorted(required))}"}
    return {"dataset_type": "unknown", "confidence": 0.0, "reason": "no schema signature matched"}


def inspect_uploaded_file(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    fmt = detect_file_format(target)
    result: dict[str, Any] = {
        "status": "unsupported_format" if fmt == "unsupported" else "inspected",
        "path": str(target), "filename": target.name, "format": fmt, "size": target.stat().st_size,
        "checksum": calculate_upload_checksum(target), "media_type": mimetypes.guess_type(target.name)[0] or "application/octet-stream",
        "encoding": detect_file_encoding(target) if fmt in {"csv", "tsv", "json", "yaml", "geojson", "kml"} else None,
    }
    if fmt in {"csv", "tsv", "xlsx", "json"}:
        structure = detect_table_structure(target)
        result["columns"] = structure.get("columns", [])
        result["rows"] = structure.get("rows")
        result["sheets"] = structure.get("sheets", [])
    elif fmt in {"geojson", "zip_shapefile", "gpkg", "kml", "kmz"}:
        result["vector"] = detect_vector_structure(target)
    elif fmt in {"geotiff", "ascii_grid", "netcdf", "hdf5"}:
        result["raster"] = detect_raster_structure(target)
    result["classification"] = classify_uploaded_dataset(target)
    return result


def copy_upload_to_workspace(path: str | Path, workspace_dir: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    root = Path(workspace_dir).expanduser().resolve()
    filename = sanitize_uploaded_filename(source.name)
    target = root / "raw" / filename
    if target.exists():
        if calculate_file_checksum(target) == calculate_file_checksum(source):
            raise FileExistsError(f"Raw upload already exists with the same checksum: {target}")
        raise FileExistsError(f"Raw upload filename already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    inspection = inspect_uploaded_file(target)
    dataset_id = f"ds_{inspection['checksum'][:12]}"
    record = {
        "dataset_id": dataset_id, "original_filename": source.name, "stored_filename": target.name,
        "source_type": "upload", "source_platform": "local", "upload_time": datetime.now(timezone.utc).isoformat(),
        "checksum": inspection["checksum"], "size": inspection["size"], "media_type": inspection["media_type"],
        "detected_format": inspection["format"], "user_declared_type": "", "coordinate_system": "",
        "temporal_range": None, "spatial_extent": None, "units": {}, "license": "user_supplied",
        "processing_status": "uploaded", "quality_status": "needs_mapping", "lineage_parent": None,
        "warnings": [], "raw_path": str(Path("raw") / target.name), "classification": inspection["classification"],
    }
    manifest = read_workspace_manifest(root)
    manifest.setdefault("datasets", []).append(record)
    write_workspace_manifest(root, manifest)
    target.chmod(target.stat().st_mode & ~0o222)
    return record


def write_upload_inspection_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "upload_inspection.json"
    md_path = output / "upload_inspection.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text("\n".join(["# Upload Inspection", "", *[f"- {key}: `{value}`" for key, value in result.items() if key not in {"vector", "raster"}]]) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
