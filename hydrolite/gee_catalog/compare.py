from __future__ import annotations

from hydrolite.gee_catalog.loader import get_catalog_dataset


def _values(records, key): return {row["asset_id"]: row.get(key) for row in records}
def compare_temporal_coverage(records): return _values(records, "start_date") | {f"{row['asset_id']}:end": row.get("end_date") for row in records}
def compare_spatial_resolution(records): return _values(records, "nominal_scale_m")
def compare_bands(records): return {row["asset_id"]: [item.get("name") if isinstance(item, dict) else item for item in row.get("bands", [])] for row in records}
def compare_units(records): return {row["asset_id"]: [item.get("unit") for item in row.get("bands", []) if isinstance(item, dict)] for row in records}
def compare_license(records): return _values(records, "license_text")
def compare_status(records): return _values(records, "status")


def compare_hydrolite_suitability(records, context=None):
    return {row["asset_id"]: {"use_cases": row.get("hydrolite_use_cases", []), "limitations": row.get("warnings", []) + ["runtime_footprint_check_required"]} for row in records}


def compare_datasets(asset_ids: list[str]) -> dict:
    if len(asset_ids) > 5: raise ValueError("At most five datasets can be compared.")
    records = [record for asset_id in asset_ids if (record := get_catalog_dataset(asset_id))]
    return {"status": "passed" if records else "not_found", "records": records, "differences": {"temporal_coverage": compare_temporal_coverage(records), "nominal_scale_m": compare_spatial_resolution(records), "bands": compare_bands(records), "units": compare_units(records), "license": compare_license(records), "status": compare_status(records), "hydrolite_suitability": compare_hydrolite_suitability(records)}}


def compare_assets(asset_ids: list[str]) -> list[dict]: return compare_datasets(asset_ids)["records"]
def write_comparison_table(result: dict) -> list[dict]: return result.get("records", [])
