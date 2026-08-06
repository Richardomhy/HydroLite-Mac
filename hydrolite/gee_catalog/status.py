from __future__ import annotations

from hydrolite.gee_catalog.loader import CACHE, FIXTURE, load_catalog


def catalog_status() -> dict:
    return {"status": "offline_catalog_available", "authentication": "authentication_required_for_gee_compute", "source": "gs://earthengine-stac/catalog.json", "records": len(load_catalog()), "cache": str(CACHE), "fixture": str(FIXTURE), "using_cache": CACHE.exists()}
