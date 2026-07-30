from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import json

import pandas as pd


_GROUPS = {
    "spatial": ["watershed_boundary", "administrative_boundary", "subbasins", "reaches", "river_network", "waterbody_boundary", "reservoir_boundary", "monitoring_points", "pollution_sources", "outlet_points"],
    "terrain": ["dem", "slope", "aspect", "flow_direction", "flow_accumulation", "landform"],
    "meteorology": ["rainfall_observed", "rainfall_forecast", "rainfall_ensemble", "temperature", "humidity", "wind", "radiation", "pressure", "evapotranspiration", "snow", "meteorological_station_metadata", "daily_meteorology", "potential_evapotranspiration", "actual_evapotranspiration", "climate_forecast_ensemble", "drought_scenario"],
    "hydrology": ["streamflow_observed", "water_level_observed", "reservoir_level", "reservoir_storage", "reservoir_release", "groundwater_level", "soil_moisture", "baseflow", "rating_curve", "flood_event_catalog", "discharge_rating_curve", "reservoir_operation_observations", "initial_condition_observations", "event_quality_flags", "data_assimilation_observations", "soil_moisture_observed", "groundwater_storage", "baseflow_observed", "reservoir_daily_balance", "drought_index_observed", "drought_event_catalog"],
    "land_soil": ["land_use", "land_cover", "soil_type", "soil_properties", "curve_number", "imperviousness", "RUSLE_R", "RUSLE_K", "RUSLE_LS", "RUSLE_C", "RUSLE_P"],
    "water_environment": ["water_quality_observations", "pollutant_sources", "point_source_discharge", "nonpoint_source_parameters", "wastewater_outlets", "agricultural_sources", "livestock_sources", "aquaculture_sources", "sediment_observations", "nutrient_observations"],
    "reservoir_channel": ["stage_area_volume", "stage_discharge", "storage_discharge", "cross_sections", "roughness", "gate_operations", "reservoir_rules"],
    "model": ["hydrolite_project", "hec_hms_project", "hec_dss", "swmm_inp", "observed_model_pair", "calibration_parameters"],
    "remote_sensing": ["ICESat2_ATL03", "ICESat2_ATL13", "ICESat2_ATL24", "satellite_image", "NDVI", "surface_water_extent", "remote_sensing_product", "vegetation_index_timeseries"],
}

_FIELDS = {
    "rainfall_observed": ["timestamp", "rainfall_mm"],
    "rainfall_forecast": ["issue_time", "valid_time", "lead_time_hr", "precipitation_mm"],
    "rainfall_ensemble": ["valid_time", "member_id", "precipitation_mm"],
    "streamflow_observed": ["timestamp", "flow_cms"],
    "water_level_observed": ["timestamp", "water_level_m"],
    "flood_event_catalog": ["event_id", "rainfall_start", "rainfall_end"],
    "discharge_rating_curve": ["station_id", "stage_m", "flow_cms"],
    "reservoir_operation_observations": ["timestamp", "reservoir_id", "storage_m3", "release_cms"],
    "initial_condition_observations": ["event_id", "variable", "value"],
    "event_quality_flags": ["event_id", "quality_flag"],
    "data_assimilation_observations": ["timestamp", "station_id", "variable", "value", "uncertainty"],
    "subbasins": ["subbasin_id", "area_km2"],
    "reaches": ["reach_id"],
    "monitoring_points": ["station_id", "longitude", "latitude"],
    "stage_area_volume": ["stage_m", "area_m2", "volume_m3"],
    "stage_discharge": ["stage_m", "discharge_cms"],
    "water_quality_observations": ["timestamp", "station_id", "concentration_mg_l"],
    "soil_properties": ["soil_id"],
    "daily_meteorology": ["date", "subbasin_id", "precipitation_mm", "temperature_min_c", "temperature_max_c", "temperature_mean_c", "quality_status", "source"],
    "potential_evapotranspiration": ["date", "subbasin_id", "potential_et_mm", "quality_status", "source"],
    "actual_evapotranspiration": ["date", "subbasin_id", "actual_et_mm", "quality_status", "source"],
    "soil_moisture_observed": ["date", "subbasin_id", "soil_moisture_fraction", "quality_status", "source"],
    "groundwater_storage": ["date", "subbasin_id", "groundwater_storage_mm", "quality_status", "source"],
    "groundwater_level": ["date", "station_id", "groundwater_level_m", "quality_status", "source"],
    "baseflow_observed": ["date", "station_id", "baseflow_cms", "quality_status", "source"],
    "reservoir_daily_balance": ["date", "reservoir_id", "inflow_cms", "release_cms", "storage_m3", "quality_status", "source"],
    "vegetation_index_timeseries": ["date", "subbasin_id", "ndvi", "quality_status", "source"],
    "drought_index_observed": ["date", "subbasin_id", "index_name", "index_value", "quality_status", "source"],
    "climate_forecast_ensemble": ["issue_time", "valid_start", "valid_end", "lead_month", "member_id", "variable", "value", "unit", "subbasin_id", "source", "forecast_system", "initialization_time", "scenario_type", "bias_correction", "quality_status"],
    "drought_scenario": ["date", "subbasin_id", "member_id", "scenario_type", "precipitation_mm"],
    "drought_event_catalog": ["event_id", "start", "end", "duration", "minimum_index", "dominant_drought_type"],
}

_FORMATS = {
    "spatial": ["geojson", "gpkg", "zip_shapefile", "kml", "kmz", "csv"],
    "terrain": ["geotiff", "ascii_grid", "netcdf"],
    "meteorology": ["csv", "xlsx", "json", "netcdf"],
    "hydrology": ["csv", "xlsx", "json", "netcdf"],
    "land_soil": ["csv", "xlsx", "geojson", "geotiff"],
    "water_environment": ["csv", "xlsx", "geojson"],
    "reservoir_channel": ["csv", "xlsx", "geojson"],
    "model": ["yaml", "hms", "inp", "dss"],
    "remote_sensing": ["hdf5", "geotiff", "netcdf"],
}

_REGISTRY: dict[str, dict[str, Any]] = {}


def _default_spec(dataset_type_id: str, domain: str) -> dict[str, Any]:
    system = domain in {"terrain", "remote_sensing", "meteorology"}
    return {
        "dataset_type_id": dataset_type_id,
        "display_name_zh": dataset_type_id.replace("_", " "),
        "display_name_en": dataset_type_id.replace("_", " ").title(),
        "domain": domain,
        "purpose": f"Standard input for {dataset_type_id}.",
        "upload_requirement": "optional_user_upload" if system else "user_upload_required",
        "system_retrievable": system,
        "platforms": ["GEE", "Earthdata", "CDS", "STAC"] if system else ["local"],
        "supported_formats": _FORMATS[domain],
        "required_fields": _FIELDS.get(dataset_type_id, []),
        "optional_fields": ["source", "quality_status", "units"],
        "standard_units": {},
        "crs_requirement": "required for spatial/raster data" if domain in {"spatial", "terrain", "remote_sensing"} else "not_applicable",
        "temporal_requirement": "timestamp required for time series" if domain in {"meteorology", "hydrology", "water_environment"} else "not_applicable",
        "size_guidance": "Use bounded project-scale files; large remote data should stay external.",
        "example_files": [f"templates/data_upload/{dataset_type_id}.csv"],
        "validation_rules": ["format", "schema", "units", "provenance"],
        "quality_levels": ["ready", "ready_with_warnings", "needs_mapping", "incomplete", "invalid"],
        "model_uses": [],
        "missing_impact": "The dependent model remains incomplete.",
        "alternatives": ["system retrieval"] if system else [],
        "interpretation_zh": f"{dataset_type_id} 数据用于模型输入准备；上传后先校验再标准化。",
        "interpretation_en": f"{dataset_type_id} is validated and standardized before model use.",
    }


for _domain, _ids in _GROUPS.items():
    for _id in _ids:
        _REGISTRY[_id] = _default_spec(_id, _domain)


def validate_dataset_type_spec(spec: dict[str, Any]) -> dict[str, Any]:
    required = {"dataset_type_id", "display_name_zh", "display_name_en", "domain", "supported_formats", "required_fields"}
    missing = sorted(required - set(spec))
    return {"status": "passed" if not missing else "failed", "missing": missing}


def register_dataset_type(spec: dict[str, Any]) -> dict[str, Any]:
    check = validate_dataset_type_spec(spec)
    if check["status"] == "failed":
        raise ValueError(f"Dataset type spec missing: {', '.join(check['missing'])}")
    _REGISTRY[spec["dataset_type_id"]] = deepcopy(spec)
    return deepcopy(spec)


def list_dataset_types(domain: str | None = None) -> list[dict[str, Any]]:
    return [deepcopy(spec) for spec in _REGISTRY.values() if domain is None or spec["domain"] == domain]


def get_dataset_type(dataset_type_id: str) -> dict[str, Any]:
    if dataset_type_id not in _REGISTRY:
        raise KeyError(f"Unknown dataset type: {dataset_type_id}")
    return deepcopy(_REGISTRY[dataset_type_id])


def get_supported_formats(dataset_type_id: str) -> list[str]:
    return get_dataset_type(dataset_type_id)["supported_formats"]


def get_required_fields(dataset_type_id: str) -> list[str]:
    return get_dataset_type(dataset_type_id)["required_fields"]


def get_optional_fields(dataset_type_id: str) -> list[str]:
    return get_dataset_type(dataset_type_id)["optional_fields"]


def get_example_files(dataset_type_id: str) -> list[str]:
    return get_dataset_type(dataset_type_id)["example_files"]


def get_dataset_interpretation(dataset_type_id: str, language: str = "zh") -> str:
    return get_dataset_type(dataset_type_id)[f"interpretation_{'zh' if language == 'zh' else 'en'}"]


def write_data_registry_report(output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = list_dataset_types()
    flat = [{**row, "supported_formats": ", ".join(row["supported_formats"]), "required_fields": ", ".join(row["required_fields"]), "platforms": ", ".join(row["platforms"])} for row in rows]
    registry = output / "data_type_registry.xlsx"
    formats = output / "supported_formats.xlsx"
    pd.DataFrame(flat).to_excel(registry, index=False)
    pd.DataFrame([{"dataset_type_id": row["dataset_type_id"], "format": fmt} for row in rows for fmt in row["supported_formats"]]).to_excel(formats, index=False)
    (output / "data_type_registry.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"registry": registry, "formats": formats}
