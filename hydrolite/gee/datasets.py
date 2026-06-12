from __future__ import annotations

from typing import Any


_DATASETS: dict[str, dict[str, Any]] = {
    "DEM": {
        "dataset_name": "DEM",
        "gee_id": "USGS/SRTMGL1_003",
        "data_type": "Image",
        "spatial_resolution": "30 m",
        "temporal_resolution": "static",
        "bands": ["elevation"],
        "notes": "SRTM DEM for terrain and elevation statistics.",
    },
    "surface_water": {
        "dataset_name": "surface_water",
        "gee_id": "JRC/GSW1_4/GlobalSurfaceWater",
        "data_type": "Image",
        "spatial_resolution": "30 m",
        "temporal_resolution": "1984-present summary layers",
        "bands": ["occurrence", "change_abs", "change_norm", "seasonality", "recurrence", "transition", "max_extent"],
        "notes": "JRC Global Surface Water occurrence and change metrics.",
    },
    "precipitation": {
        "dataset_name": "precipitation",
        "gee_id": "UCSB-CHG/CHIRPS/DAILY",
        "data_type": "ImageCollection",
        "spatial_resolution": "0.05 degree",
        "temporal_resolution": "daily",
        "bands": ["precipitation"],
        "notes": "CHIRPS daily rainfall; used for recent 30-day basin precipitation summaries.",
    },
    "temperature": {
        "dataset_name": "temperature",
        "gee_id": "ECMWF/ERA5_LAND/DAILY_AGGR",
        "data_type": "ImageCollection",
        "spatial_resolution": "0.1 degree",
        "temporal_resolution": "daily",
        "bands": ["temperature_2m"],
        "notes": "ERA5-Land daily 2 m air temperature. Values are Kelvin in GEE and are converted to Celsius.",
    },
    "landcover": {
        "dataset_name": "landcover",
        "gee_id": "ESA/WorldCover/v200",
        "data_type": "ImageCollection",
        "spatial_resolution": "10 m",
        "temporal_resolution": "annual snapshot",
        "bands": ["Map"],
        "notes": "ESA WorldCover land cover classes.",
    },
    "ndvi": {
        "dataset_name": "ndvi",
        "gee_id": "MODIS/061/MOD13Q1",
        "data_type": "ImageCollection",
        "spatial_resolution": "250 m",
        "temporal_resolution": "16 day",
        "bands": ["NDVI", "EVI"],
        "notes": "MODIS vegetation indices.",
    },
}


def list_supported_datasets() -> list[str]:
    return list(_DATASETS)


def get_dataset_metadata(dataset_name: str) -> dict[str, Any]:
    normalized = dataset_name.lower()
    aliases = {
        "surface water": "surface_water",
        "surface_water": "surface_water",
        "dem": "DEM",
        "precip": "precipitation",
        "rainfall": "precipitation",
        "temp": "temperature",
        "era5": "temperature",
        "era5_land": "temperature",
    }
    key = aliases.get(normalized, dataset_name)
    for name, metadata in _DATASETS.items():
        if name.lower() == str(key).lower():
            return dict(metadata)
    raise KeyError(f"Unsupported GEE dataset: {dataset_name}")
