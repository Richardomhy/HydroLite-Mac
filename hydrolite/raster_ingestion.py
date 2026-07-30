from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import math
import shutil

import numpy as np


def _ascii_header(path: Path) -> tuple[dict[str, float], np.ndarray]:
    header: dict[str, float] = {}
    with path.open(encoding="utf-8") as handle:
        lines = handle.readlines()
    for line in lines[:6]:
        key, value = line.split()[:2]
        header[key.lower()] = float(value)
    return header, np.loadtxt(path, skiprows=6)


def inspect_raster(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix == ".asc":
        try:
            header, values = _ascii_header(target)
            nodata = header.get("nodata_value")
            clean = values[values != nodata] if nodata is not None else values
            return {"status": "passed", "backend": "ascii_grid", "format": "ascii_grid", "crs": None, "crs_status": "crs_missing", "width": int(header["ncols"]), "height": int(header["nrows"]), "resolution": header.get("cellsize"), "nodata": nodata, "min": float(clean.min()), "max": float(clean.max()), "dtype": str(values.dtype)}
        except Exception as exc:
            return {"status": "invalid", "format": "ascii_grid", "error": str(exc)}
    try:
        import rasterio
        with rasterio.open(target) as dataset:
            data = dataset.read(1, masked=True)
            return {"status": "passed", "backend": "rasterio", "format": dataset.driver, "crs": str(dataset.crs) if dataset.crs else None, "crs_status": "passed" if dataset.crs else "crs_missing", "width": dataset.width, "height": dataset.height, "resolution": dataset.res, "nodata": dataset.nodata, "min": float(data.min()), "max": float(data.max()), "dtype": str(dataset.dtypes[0]), "extent": list(dataset.bounds)}
    except Exception as exc:
        kind = {".nc": "netcdf", ".h5": "hdf5", ".hdf5": "hdf5", ".tif": "geotiff", ".tiff": "geotiff"}.get(suffix, "raster")
        return {"status": "optional_backend_required", "format": kind, "error": str(exc)}


def validate_raster(path: str | Path, dataset_type: str) -> dict[str, Any]:
    info = inspect_raster(path)
    warnings: list[str] = []
    if info.get("crs_status") == "crs_missing":
        warnings.append("CRS is missing.")
    crs = str(info.get("crs") or "")
    if dataset_type in {"dem", "slope", "flow_accumulation", "RUSLE_LS"} and ("4326" in crs or "longlat" in crs.lower()):
        warnings.append("Geographic CRS must not be used directly for length or area calculations; reproject first.")
    return {**info, "quality_status": "ready_with_warnings" if info.get("status") == "passed" and warnings else ("ready" if info.get("status") == "passed" else info.get("status")), "warnings": warnings}


def detect_raster_nodata(path: str | Path) -> Any:
    return inspect_raster(path).get("nodata")


def calculate_raster_statistics(path: str | Path) -> dict[str, Any]:
    info = inspect_raster(path)
    return {key: info.get(key) for key in ("status", "min", "max", "nodata", "dtype")}


def compare_raster_grids(paths: list[str | Path]) -> dict[str, Any]:
    infos = [inspect_raster(path) for path in paths]
    keys = ("crs", "width", "height", "resolution")
    aligned = all(all(info.get(key) == infos[0].get(key) for key in keys) for info in infos[1:]) if infos else False
    return {"status": "aligned" if aligned else "different_grids", "rasters": infos}


def align_raster_to_reference(path: str | Path, reference: str | Path, output_path: str | Path, method: str) -> Path:
    try:
        import rasterio
        from rasterio.warp import reproject, Resampling
    except ImportError as exc:
        raise RuntimeError("Raster alignment requires optional rasterio.") from exc
    methods = {"nearest": Resampling.nearest, "bilinear": Resampling.bilinear}
    if method not in methods:
        raise ValueError("method must be nearest or bilinear")
    with rasterio.open(path) as source, rasterio.open(reference) as ref:
        profile = ref.profile.copy()
        with rasterio.open(output_path, "w", **profile) as target:
            for band in range(1, source.count + 1):
                reproject(rasterio.band(source, band), rasterio.band(target, band), src_transform=source.transform, src_crs=source.crs, dst_transform=ref.transform, dst_crs=ref.crs, resampling=methods[method])
    return Path(output_path)


def clip_raster_to_boundary(path: str | Path, boundary: str | Path, output_path: str | Path) -> Path:
    raise RuntimeError("Raster clipping requires optional rasterio/geopandas or qgis_process.")


def write_raster_quality_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "raster_quality.json"
    xlsx_path = output / "raster_quality.xlsx"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    import pandas as pd
    pd.DataFrame([result]).to_excel(xlsx_path, index=False)
    return {"json": json_path, "xlsx": xlsx_path}
