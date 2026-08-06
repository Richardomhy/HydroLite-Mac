from __future__ import annotations

from hydrolite.gee_catalog.index import build_index


def generate_ee_code(asset_id: str, config: str | None = None) -> dict:
    record = build_index().get(asset_id.lower())
    if not record: return {"status": "not_found", "asset_id": asset_id}
    return {"status": "authentication_required", "asset_id": asset_id, "config": config, "snippet": f"import ee\n# Authenticate locally; do not commit credentials.\nimage = ee.ImageCollection('{record['asset_id']}')\n"}
