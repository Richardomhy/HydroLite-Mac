from __future__ import annotations

from hydrolite.gee_catalog.loader import get_catalog_dataset


def generate_ee_code(asset_id: str, config: str | None = None, band: str | None = None, language: str = "python") -> dict:
    record = get_catalog_dataset(asset_id)
    if not record: return {"status": "not_found", "asset_id": asset_id}
    bands = [item.get("name") if isinstance(item, dict) else item for item in record.get("bands", [])]
    if band is None: return {"status": "band_selection_required", "asset_id": asset_id, "available_bands": bands, "reason": "Select a catalog-listed band before generating executable analysis code."}
    if band and band not in bands: return {"status": "invalid_band", "asset_id": asset_id, "available_bands": bands}
    constructor = "ee.FeatureCollection" if record.get("dataset_type") == "FeatureCollection" else "ee.ImageCollection" if record.get("dataset_type") == "ImageCollection" else "ee.Image"
    selected = f".select('{band}')" if band else ""
    if language == "javascript":
        snippet = f"// Source: {record.get('official_catalog_url')}\n// Units/resolution: {record.get('license_text')}; {record.get('nominal_scale_m')} m\nvar dataset = {constructor}('{record['asset_id']}'){selected};\n// Before execution: supply a bounded geometry and date range; do not export automatically.\n"
    else:
        snippet = f"import ee\n# Source: {record.get('official_catalog_url')}\n# License reminder: {record.get('license_text')}\n# Before execution: authenticate locally and supply a bounded geometry/date range.\ndataset = {constructor}('{record['asset_id']}'){selected}\n"
    return {"status": "authentication_required", "asset_id": asset_id, "language": language, "config": config, "snippet": snippet, "execution": "not_executed", "source": record.get("official_catalog_url"), "nominal_scale_m": record.get("nominal_scale_m")}
