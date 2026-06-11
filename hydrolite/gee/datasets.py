from __future__ import annotations

from typing import Any


_DATASETS: dict[str, dict[str, Any]] = {
    "DEM": {
        "examples": ["NASA/NASADEM_HGT/001", "USGS/SRTMGL1_003"],
        "description": "Elevation and terrain derivatives for basin preprocessing.",
    },
    "landcover": {
        "examples": ["ESA/WorldCover/v200", "MODIS/061/MCD12Q1"],
        "description": "Land cover classes for runoff parameter support.",
    },
    "precipitation": {
        "examples": ["NASA/GPM_L3/IMERG_V06", "UCSB-CHG/CHIRPS/DAILY"],
        "description": "Satellite or blended precipitation forcing.",
    },
    "ndvi": {
        "examples": ["MODIS/061/MOD13Q1", "COPERNICUS/S2_SR_HARMONIZED"],
        "description": "Vegetation index time series.",
    },
    "water_index": {
        "examples": ["COPERNICUS/S2_SR_HARMONIZED"],
        "description": "Placeholder for NDWI/MNDWI style derived water indices.",
    },
    "surface_water": {
        "examples": ["JRC/GSW1_4/GlobalSurfaceWater"],
        "description": "Long-term surface water occurrence and change products.",
    },
}


def list_supported_datasets() -> list[str]:
    return list(_DATASETS)


def get_dataset_metadata(dataset_name: str) -> dict[str, Any]:
    for name, metadata in _DATASETS.items():
        if name.lower() == dataset_name.lower():
            return {"name": name, **metadata}
    raise KeyError(f"Unsupported GEE dataset placeholder: {dataset_name}")
