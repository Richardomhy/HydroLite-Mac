from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def _iter_coordinates(geometry: dict[str, Any]):
    coords = geometry.get("coordinates", [])
    if geometry.get("type") == "Point":
        yield coords
    else:
        stack = [coords]
        while stack:
            item = stack.pop()
            if not item:
                continue
            if isinstance(item[0], (int, float)) and len(item) >= 2:
                yield item
            else:
                stack.extend(item)


def read_geojson_boundary(path: str | Path) -> dict[str, Any]:
    boundary_path = Path(path).expanduser()
    if not boundary_path.exists():
        return {
            "status": "missing",
            "path": str(boundary_path),
            "error_message": f"Boundary file not found: {boundary_path}",
            "geojson": None,
        }
    try:
        data = json.loads(boundary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "failed",
            "path": str(boundary_path),
            "error_message": f"Failed to read GeoJSON: {exc}",
            "geojson": None,
        }
    if data.get("type") not in {"FeatureCollection", "Feature", "Polygon", "MultiPolygon"}:
        return {
            "status": "failed",
            "path": str(boundary_path),
            "error_message": "GeoJSON must be FeatureCollection, Feature, Polygon, or MultiPolygon.",
            "geojson": data,
        }
    return {"status": "available", "path": str(boundary_path), "error_message": "", "geojson": data}


def get_boundary_bbox(path: str | Path) -> dict[str, Any]:
    boundary_path = Path(path).expanduser()
    if not boundary_path.exists():
        return {
            "status": "missing",
            "path": str(boundary_path),
            "bbox": None,
            "error_message": f"Boundary file not found: {boundary_path}",
        }
    try:
        import geopandas as gpd

        gdf = gpd.read_file(boundary_path)
        minx, miny, maxx, maxy = gdf.to_crs("EPSG:4326").total_bounds
        return {
            "status": "available",
            "path": str(boundary_path),
            "bbox": [float(minx), float(miny), float(maxx), float(maxy)],
            "source": "geopandas",
            "error_message": "",
        }
    except Exception:
        loaded = read_geojson_boundary(boundary_path)
        if loaded["status"] != "available":
            return {
                "status": loaded["status"],
                "path": str(boundary_path),
                "bbox": None,
                "source": "json",
                "error_message": loaded["error_message"],
            }
        features = []
        data = loaded["geojson"]
        if data["type"] == "FeatureCollection":
            features = data.get("features", [])
        elif data["type"] == "Feature":
            features = [data]
        else:
            features = [{"geometry": data}]
        xs: list[float] = []
        ys: list[float] = []
        for feature in features:
            geometry = feature.get("geometry") or {}
            for coord in _iter_coordinates(geometry):
                xs.append(float(coord[0]))
                ys.append(float(coord[1]))
        if not xs or not ys:
            return {
                "status": "failed",
                "path": str(boundary_path),
                "bbox": None,
                "source": "json",
                "error_message": "No coordinates found in GeoJSON boundary.",
            }
        return {
            "status": "available",
            "path": str(boundary_path),
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "source": "json",
            "error_message": "",
        }


def load_basin_boundary(path: str | Path) -> dict[str, Any]:
    boundary_path = Path(path).expanduser()
    bbox = get_boundary_bbox(boundary_path)
    return {
        "path": str(boundary_path),
        "exists": boundary_path.exists(),
        "suffix": boundary_path.suffix.lower(),
        "status": bbox["status"],
        "bbox": bbox.get("bbox"),
        "error_message": bbox.get("error_message", ""),
    }


def summarize_basin_placeholder(boundary_path: str | Path) -> dict[str, Any]:
    boundary = load_basin_boundary(boundary_path)
    return {
        **boundary,
        "message": "Basin boundary bbox is available for GEE summary requests."
        if boundary["status"] == "available"
        else "Basin boundary is unavailable.",
    }
