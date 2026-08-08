from __future__ import annotations

from hydrolite.gee_catalog.loader import inspect_catalog_availability, load_catalog_manifest


def catalog_status() -> dict:
    availability = inspect_catalog_availability(); manifest = load_catalog_manifest()
    return {**availability, "authentication": "authentication_required_for_gee_compute", "source": "gs://earthengine-stac/catalog.json", "manifest": manifest}
