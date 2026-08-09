"""Relative susceptibility prediction and lightweight spatial outputs."""

from __future__ import annotations

import json
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RELATIVE_CLASSES = ("very_low", "low", "moderate", "high", "very_high")


def predict_susceptibility(model: Any, data: Any, factors: list[str], calibrator: Any | None = None) -> np.ndarray:
    probability = model.predict_proba(pd.DataFrame(data)[factors])
    return np.clip(calibrator.predict(probability) if calibrator is not None else probability, 0, 1)


def classify_relative_susceptibility(probability: Any) -> pd.Categorical:
    values = np.clip(np.asarray(probability, dtype=float), 0, 1)
    return pd.cut(values, bins=[-1e-12, .2, .4, .6, .8, 1.0], labels=RELATIVE_CLASSES, include_lowest=True)


def write_susceptibility_geojson(data: Any, output_path: str | Path) -> Path:
    frame = pd.DataFrame(data); path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for row in frame.itertuples(index=False):
        features.append({"type": "Feature", "properties": {"point_id": str(row.point_id), "probability": float(row.probability), "relative_susceptibility_class": str(row.relative_susceptibility_class), "block_id": str(getattr(row, "block_id", "unknown")), "synthetic_demo": bool(getattr(row, "synthetic_demo", True)), "is_flood_risk": False}, "geometry": {"type": "Point", "coordinates": [float(row.longitude), float(row.latitude)]}})
    path.write_text(json.dumps({"type": "FeatureCollection", "name": "relative_flood_susceptibility_not_risk", "features": features}, ensure_ascii=False), encoding="utf-8")
    return path


def write_susceptibility_raster_if_available(data: Any, output_path: str | Path, width: int = 120, height: int = 80) -> dict[str, Any]:
    path = Path(output_path)
    if find_spec("rasterio") is None: return {"status": "optional_dependency_missing", "path": None, "dependency": "rasterio"}
    import rasterio
    from rasterio.transform import from_bounds
    frame = pd.DataFrame(data); left, right = float(frame.longitude.min()), float(frame.longitude.max()); bottom, top = float(frame.latitude.min()), float(frame.latitude.max())
    x_index = np.clip(((frame.longitude - left) / max(right - left, 1e-12) * (width - 1)).astype(int), 0, width - 1); y_index = np.clip(((top - frame.latitude) / max(top - bottom, 1e-12) * (height - 1)).astype(int), 0, height - 1)
    total = np.zeros((height, width), dtype=float); count = np.zeros((height, width), dtype=int)
    for x, y, probability in zip(x_index, y_index, frame.probability): total[y, x] += float(probability); count[y, x] += 1
    raster = np.full((height, width), np.nan, dtype="float32"); mask = count > 0; raster[mask] = (total[mask] / count[mask]).astype("float32")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=height, width=width, count=1, dtype="float32", crs="EPSG:4326", transform=from_bounds(left, bottom, right, top, width, height), nodata=np.nan) as target: target.write(raster, 1); target.update_tags(product="relative_flood_susceptibility", flood_risk="false", synthetic_demo="true")
    return {"status": "passed", "path": str(path), "nonempty_cells": int(mask.sum()), "crs": "EPSG:4326"}


def validate_susceptibility_map(data: Any) -> dict[str, Any]:
    frame = pd.DataFrame(data); missing = sorted({"point_id", "longitude", "latitude", "probability", "relative_susceptibility_class"} - set(frame)); invalid = int((~frame.probability.between(0, 1)).sum()) if not missing else 0
    return {"status": "passed" if not missing and not invalid else "failed", "missing_columns": missing, "invalid_probability_count": invalid, "relative_classes": sorted(frame.relative_susceptibility_class.astype(str).unique().tolist()) if not missing else [], "susceptibility_is_risk": False}
