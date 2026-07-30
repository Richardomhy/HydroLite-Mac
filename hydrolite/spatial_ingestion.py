from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import math
import shutil


def _geojson(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _coords(value: Any):
    if isinstance(value, (list, tuple)) and value and all(isinstance(item, (int, float)) for item in value):
        yield float(value[0]), float(value[1])
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _coords(item)


def inspect_crs(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.suffix.lower() in {".geojson", ".json", ".kml", ".kmz"}:
        return {"status": "passed", "crs": "EPSG:4326", "rule": "GeoJSON/KML/KMZ default WGS84"}
    if target.suffix.lower() == ".zip":
        import zipfile
        with zipfile.ZipFile(target) as archive:
            prj = next((name for name in archive.namelist() if name.lower().endswith(".prj")), None)
        return {"status": "passed" if prj else "crs_missing", "crs": "declared_in_prj" if prj else None}
    try:
        import geopandas as gpd
        crs = gpd.read_file(target, rows=1).crs
        return {"status": "passed" if crs else "crs_missing", "crs": str(crs) if crs else None}
    except Exception as exc:
        return {"status": "optional_backend_required", "crs": None, "error": str(exc)}


def inspect_extent(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.suffix.lower() in {".geojson", ".json"}:
        points = [point for feature in _geojson(target).get("features", []) for point in _coords((feature.get("geometry") or {}).get("coordinates", []))]
        if not points:
            return {"status": "empty", "extent": None}
        xs, ys = zip(*points)
        return {"status": "passed", "extent": [min(xs), min(ys), max(xs), max(ys)], "coordinates_suspicious": any(abs(x) > 180 or abs(y) > 90 for x, y in points)}
    try:
        import geopandas as gpd
        return {"status": "passed", "extent": list(map(float, gpd.read_file(target).total_bounds))}
    except Exception as exc:
        return {"status": "optional_backend_required", "extent": None, "error": str(exc)}


def inspect_geometry_types(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.suffix.lower() in {".geojson", ".json"}:
        types = sorted({(feature.get("geometry") or {}).get("type", "null") for feature in _geojson(target).get("features", [])})
        return {"status": "passed", "geometry_types": types}
    try:
        import geopandas as gpd
        return {"status": "passed", "geometry_types": sorted(gpd.read_file(target).geom_type.dropna().unique())}
    except Exception as exc:
        return {"status": "optional_backend_required", "geometry_types": [], "error": str(exc)}


def validate_geometry(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.suffix.lower() in {".geojson", ".json"}:
        data = _geojson(target)
        features = data.get("features", [])
        empty = sum(not (feature.get("geometry") or {}).get("coordinates") for feature in features)
        return {"status": "passed" if features and not empty else "invalid", "feature_count": len(features), "empty_geometry_count": empty, "validity_backend": "lightweight"}
    try:
        import geopandas as gpd
        frame = gpd.read_file(target)
        invalid = int((~frame.geometry.is_valid).sum())
        empty = int(frame.geometry.is_empty.sum())
        return {"status": "passed" if not invalid and not empty else "invalid", "feature_count": len(frame), "invalid_geometry_count": invalid, "empty_geometry_count": empty, "validity_backend": "geopandas"}
    except Exception as exc:
        return {"status": "optional_backend_required", "error": str(exc)}


def repair_geometry_copy(path: str | Path, output_path: str | Path) -> Path:
    try:
        import geopandas as gpd
        frame = gpd.read_file(path)
        frame.geometry = frame.geometry.buffer(0)
        frame.to_file(output_path, driver="GeoJSON" if Path(output_path).suffix.lower() == ".geojson" else None)
    except ImportError:
        shutil.copy2(path, output_path)
    return Path(output_path)


def reproject_dataset(path: str | Path, output_path: str | Path, target_crs: str) -> Path:
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError("Reprojection requires optional GIS dependencies or qgis_process.") from exc
    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError("CRS is missing; user confirmation is required before reprojection.")
    frame.to_crs(target_crs).to_file(output_path)
    return Path(output_path)


def clip_dataset(path: str | Path, boundary: str | Path, output_path: str | Path) -> Path:
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError("Clipping requires optional GIS dependencies or qgis_process.") from exc
    gpd.clip(gpd.read_file(path), gpd.read_file(boundary)).to_file(output_path)
    return Path(output_path)


def calculate_spatial_coverage(dataset: str | Path, boundary: str | Path) -> dict[str, Any]:
    try:
        import geopandas as gpd
        source, basin = gpd.read_file(dataset), gpd.read_file(boundary)
        if source.crs != basin.crs:
            source = source.to_crs(basin.crs)
        ratio = float(source.geometry.unary_union.intersection(basin.geometry.unary_union).area / basin.geometry.unary_union.area)
        return {"status": "passed", "coverage_fraction": ratio}
    except Exception as exc:
        return {"status": "optional_backend_required", "coverage_fraction": None, "error": str(exc)}


def validate_spatial_overlap(datasets: list[str | Path]) -> dict[str, Any]:
    extents = [inspect_extent(path) for path in datasets]
    valid = [item["extent"] for item in extents if item.get("extent")]
    if len(valid) < 2:
        return {"status": "insufficient_data", "overlap": None}
    xmin, ymin = max(item[0] for item in valid), max(item[1] for item in valid)
    xmax, ymax = min(item[2] for item in valid), min(item[3] for item in valid)
    return {"status": "passed" if xmin <= xmax and ymin <= ymax else "no_overlap", "overlap": [xmin, ymin, xmax, ymax] if xmin <= xmax and ymin <= ymax else None}


def write_spatial_quality_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "spatial_quality.json"
    md_path = output / "spatial_quality.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text("# Spatial Quality\n\n" + "\n".join(f"- {key}: `{value}`" for key, value in result.items()) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
