from __future__ import annotations

from hydrolite.gee_catalog.loader import inspect_catalog_availability, load_catalog_manifest
from hydrolite.gee_catalog.transport import detect_available_transports


def catalog_status() -> dict:
    availability = inspect_catalog_availability(); manifest = load_catalog_manifest()
    return {**availability, "compute_authentication": "authentication_required_for_gee_compute", "catalog_transport": "fixture_fallback" if availability["status"] == "fixture_only" else "available", "source": "gs://earthengine-stac/catalog/catalog.json", "manifest": manifest, "available_transports": detect_available_transports()}
