from contextlib import contextmanager
from io import BytesIO
import json

import pytest


def test_provider_profiles_and_source_matrix_have_only_four_official_sources():
    from hydrolite.connectors.registry import DataConnectorRegistry, provider_profiles, source_priority_for
    profiles = provider_profiles()
    assert set(profiles) == {"earth_engine", "copernicus_stac", "nasa_cmr", "hydrosheds"}
    required = {"provider_id", "provider_name", "authority", "base_endpoint", "access_type", "authentication",
                "supported_data_types", "search_supported", "fetch_supported", "max_auto_fetch_size",
                "license_status", "commercial_use_status", "priority", "fallback_priority", "health_status"}
    assert all(required <= row.keys() for row in profiles.values())
    assert source_priority_for("dem")[:2] == ("hydrosheds", "gee")
    assert "copernicus_stac" in source_priority_for("satellite_image")
    assert profiles["earth_engine"]["fetch_supported"] is False
    health = {row["connector_id"]: row for row in DataConnectorRegistry().health()}
    assert set(health["hydrosheds"]["supported_datasets"]) >= {"dem", "flow_direction", "flow_accumulation"}
    assert health["hydrosheds"]["provider_profile"]["provider_id"] == "hydrosheds"


def test_hydrosheds_tiles_are_bbox_derived_and_candidate_is_bounded():
    from hydrolite.connectors.public import HydroSHEDSConnector
    assert HydroSHEDSConnector.tile_candidates([113.0, 22.0, 114.0, 23.0]) == ["SW:110:20"]
    connector = HydroSHEDSConnector({"endpoint": "https://data.hydrosheds.org/file", "allowed_hosts": ["data.hydrosheds.org"],
        "provider": "HydroSHEDS", "products": {"dem": {"collection": "hydrosheds-v1-dem", "regions": {
            "asia": {"filename": "hyd_as_dem_30s.zip", "estimated_mb": 47, "bbox": [25, -12, 180, 82], "license": "HydroSHEDS v1 core product license"}}}}})
    result = connector.search({"online": True, "data_type": "dem", "bbox": [113.0, 22.0, 114.0, 23.0]})
    candidate = result["candidates"][0]
    assert result["status"] == "available"
    assert candidate.estimated_size < 50 * 1024 * 1024
    assert candidate.license_status == "known"
    assert candidate.metadata["data_origin_class"] == "derived"
    assert candidate.metadata["aoi_tile_candidates"] == ["SW:110:20"]
    assert "hydrosheds.org" in candidate.source_url


def test_hydrosheds_never_claims_coverage_outside_verified_regional_product():
    from hydrolite.connectors.public import HydroSHEDSConnector
    connector = HydroSHEDSConnector({"endpoint": "https://data.hydrosheds.org/file", "allowed_hosts": ["data.hydrosheds.org"], "products": {"dem": {"regions": {"asia": {"bbox": [25, -12, 180, 82]}}}}})
    result = connector.search({"online": True, "data_type": "dem", "bbox": [-123, 37, -122, 38]})
    assert result["status"] == "approval_required"
    assert result["candidates"] == []


def test_nasa_cmr_metadata_search_is_bounded_and_never_claims_download(monkeypatch):
    from hydrolite.connectors.public import NASACMRConnector
    payload = {"feed": {"entry": [{"id": "C123-PODAAC", "dataset_id": "GPM IMERG", "short_name": "GPM_3IMERGDF", "has_granules": True}]}}

    @contextmanager
    def fake_open(url, hosts, **kwargs):
        assert "cmr.earthdata.nasa.gov/search/collections.json" in url
        assert "bounding_box=110%2C20%2C120%2C30" in url
        yield BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr("hydrolite.connectors.public.open_public", fake_open)
    connector = NASACMRConnector({"endpoint": "https://cmr.earthdata.nasa.gov/search", "allowed_hosts": ["cmr.earthdata.nasa.gov"], "collections": {"rainfall": "GPM_3IMERGDF"}})
    result = connector.search({"online": True, "data_type": "rainfall", "bbox": [110, 20, 120, 30], "start": "2024-01-01", "end": "2024-01-02"})
    assert result["status"] == "available"
    assert result["candidates"][0].access_status == "discover_only"
    assert result["candidates"][0].metadata["data_origin_class"] == "public_remote_sensing"
    assert "project measurements" in result["candidates"][0].metadata["fitness_for_purpose"]
    fetched = connector.fetch(result["candidates"][0])
    assert fetched["status"] == "auth_required"


def test_nasa_cmr_granules_require_a_collection_scope(monkeypatch):
    from hydrolite.connectors.public import NASACMRConnector
    connector = NASACMRConnector({"endpoint": "https://cmr.earthdata.nasa.gov/search", "allowed_hosts": ["cmr.earthdata.nasa.gov"], "collections": {}})
    assert connector.search({"online": True, "granules": True, "bbox": [0, 0, 1, 1]})["status"] == "collection_required_for_granules"


def test_copernicus_stac_never_promotes_discovery_to_fetch(monkeypatch):
    from hydrolite.connectors.public import CopernicusStacConnector

    @contextmanager
    def fake_open(url, hosts, **kwargs):
        payload = {"license": "unknown"} if "/collections/" in url else {"features": [{"id": "S2", "bbox": [110, 20, 120, 30], "properties": {}, "assets": {"data": {"href": "https://stac.dataspace.copernicus.eu/data.tif", "roles": ["data"], "type": "image/tiff"}}}]}
        yield BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr("hydrolite.connectors.public.open_public", fake_open)
    connector = CopernicusStacConnector({"endpoint": "https://stac.dataspace.copernicus.eu/v1", "allowed_hosts": ["stac.dataspace.copernicus.eu"], "provider": "Copernicus", "trusted": True, "collections": {"satellite_image": "sentinel-2-l2a"}})
    result = connector.search({"online": True, "data_type": "satellite_image", "bbox": [110, 20, 120, 30]})
    assert result["candidates"][0].access_status == "discover_only"


def test_imported_public_data_keeps_origin_and_fitness(tmp_path):
    from hashlib import sha256
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.data_acquisition import import_fetched_dataset
    from hydrolite.workspace import create_workspace
    workspace = tmp_path / "workspace"
    create_workspace(workspace, "origin")
    cache = tmp_path / "cache" / "data.zip"
    cache.parent.mkdir()
    cache.write_bytes(b"not parsed here")
    digest = sha256(cache.read_bytes()).hexdigest()
    row = import_fetched_dataset({"local_path": str(cache), "checksum": digest, "candidate": {"dataset_id": "hs-dem", "provider": "HydroSHEDS", "data_type": "dem", "license": "v1 license", "license_status": "known", "metadata": {"data_origin_class": "public_remote_sensing", "fitness_for_purpose": "regional baseline"}}}, workspace, DataRequirement("dem", "dem"))
    assert row["data_origin_class"] == "public_remote_sensing"
    assert row["fitness_for_purpose"] == "regional baseline"
    assert row["project_measurement_confirmed"] is False


def test_source_fallback_rechecks_suitability_and_stops_at_first_auto_fetch():
    from hydrolite.connectors.base import DataConnector
    from hydrolite.connectors.contracts import DataRequirement
    from hydrolite.connectors.registry import DataConnectorRegistry

    class CandidateConnector(DataConnector):
        data_types = ("dem",)
        def __init__(self, connector_id, candidate): self.connector_id, self.candidate = connector_id, candidate
        def search(self, config): return {"status": "available", "candidates": [self.candidate]}

    # First provider misses the requested AOI; fallback covers it and is fetchable.
    from hydrolite.connectors.contracts import DatasetCandidate
    first = DatasetCandidate("first", "first", "first", "dem", variables=("dem",), spatial_extent=(-10, -10, 0, 0), license_status="known", trusted_provider=True, access_status="public_download")
    second = DatasetCandidate("second", "second", "second", "dem", variables=("dem",), spatial_extent=(0, 0, 2, 2), license_status="known", trusted_provider=True, access_status="public_download")
    registry = DataConnectorRegistry([CandidateConnector("first", first), CandidateConnector("second", second)])
    request = DataRequirement("dem", "dem", spatial_extent=(0.5, 0.5, 1, 1), preferred_connectors=("first", "second"))
    result = registry.recommend(request, {"online": True})
    assert [row["candidate"]["dataset_id"] for row in result["candidates"]] == ["second", "first"]
    assert result["candidates"][0]["eligible"] is True
    assert "covers requested AOI" in result["candidates"][0]["selection_reason"]


def test_provider_failure_classification_is_closed_vocabulary():
    from hydrolite.connectors.registry import classify_provider_failure
    assert classify_provider_failure("proxy_blocked") == "security_blocked"
    assert classify_provider_failure("auth_required") == "auth_required"
    assert classify_provider_failure("unsupported_format") == "unsupported"
    assert classify_provider_failure("totally_new") is None
