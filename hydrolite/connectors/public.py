"""Configured public dataset adapters. No credentials or scraping implementation."""
from dataclasses import replace
import json
from pathlib import Path
from urllib.parse import urlencode, urljoin

import yaml

from hydrolite.connectors.base import DataConnector
from hydrolite.connectors.contracts import DatasetCandidate, FetchedDataset
from hydrolite.connectors.transport import ConnectorError, open_public


def provider_config(path=None):
    source = Path(path) if path else Path(__file__).resolve().parents[2] / "config/connectors/providers.yaml"
    return (yaml.safe_load(source.read_text()) or {}).get("providers", {})


class HttpFileConnector(DataConnector):
    connector_id = "http"
    display_name = "Configured public HTTP files"
    provider = "configured"

    def __init__(self, config=None):
        self.config = provider_config().get("http", {}) if config is None else config

    def search(self, config):
        rows = []
        for item in self.config.get("datasets", []):
            if config.get("data_type") and item.get("data_type") != config["data_type"]:
                continue
            rows.append(DatasetCandidate(**{**item, "connector_id": self.connector_id, "provider": self.config.get("provider", "configured"), "trusted_provider": bool(self.config.get("trusted")), "access_status": "public_download"}))
        return {"status": "available" if rows else "provider_not_configured", "candidates": rows}

    def fetch(self, candidate, **kwargs):
        from hydrolite.dataset_cache import DatasetCache
        if candidate.license_status != "known":
            return FetchedDataset("approval_required", candidate.as_dict(), error_message="A verified reusable license is required for automatic fetch").as_dict()
        if candidate.access_status != "public_download":
            return FetchedDataset("approval_required", candidate.as_dict()).as_dict()
        cache = kwargs.pop("cache", None) or DatasetCache()
        return cache.fetch(candidate, self.config.get("allowed_hosts", []), interval=self.config.get("request_interval_seconds", 0), **kwargs)

    def healthcheck(self):
        return {**super().healthcheck(), "status": "healthy" if self.config.get("datasets") else "unavailable", "reason": "configured_public_files_only"}


class GenericStacAdapter(HttpFileConnector):
    connector_id = "stac"
    display_name = "Public STAC acquisition"

    def __init__(self, config=None):
        super().__init__(provider_config().get("earth_search", {}) if config is None else config)

    def search(self, config):
        if not config.get("online", False):
            return {"status": "offline_discovery", "candidates": []}
        kind = config.get("data_type", "dem")
        collection = self.config.get("collections", {}).get(kind)
        if not collection:
            return {"status": "unsupported", "candidates": []}
        params = {"collections": collection, "limit": min(int(config.get("limit", 5)), 20)}
        if config.get("bbox"):
            params["bbox"] = ",".join(map(str, config["bbox"]))
        else:
            return {"status": "spatial_extent_required", "candidates": []}
        if config.get("start") and config.get("end"):
            params["datetime"] = f"{config['start']}/{config['end']}"
        try:
            license_name = self._collection_license(collection)
            search_url = self.config["endpoint"].rstrip("/") + "/search?" + urlencode(params)
            with open_public(search_url, self.config["allowed_hosts"], interval=self.config.get("request_interval_seconds", 1)) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ConnectorError("size_guard", "STAC metadata too large")
                payload = json.loads(raw)
            rows = []
            for item in payload.get("features", []):
                props = item.get("properties", {})
                for name, asset in item.get("assets", {}).items():
                    if "data" not in asset.get("roles", []) and name not in {"data", "dem"}:
                        continue
                    item_license = item.get("license") or props.get("license") or license_name or "unknown"
                    normalized_license = item_license.upper()
                    restricted = item_license.lower() in {"proprietary", "restricted", "various"} or "NONCOMMERCIAL" in normalized_license or "CC-BY-NC" in normalized_license or "SA-" in normalized_license
                    recognized = any(token in normalized_license for token in ("CC0", "CC-BY-", "PDDL", "ODBL", "PUBLIC-DOMAIN"))
                    status = "restricted" if restricted else "known" if recognized else "unknown"
                    rows.append(DatasetCandidate(
                        f"{collection}/{item['id']}/{name}", "stac", self.config.get("provider", "STAC"), kind,
                        urljoin(next((link.get("href", "") for link in item.get("links", []) if link.get("rel") == "self"), search_url), asset.get("href", "")), str(props.get("version") or props.get("updated") or props.get("datetime") or ""),
                        (kind,), tuple(item.get("bbox", [])[:4]), tuple(str(props.get(key) or props.get("datetime") or "") for key in ("start_datetime", "end_datetime")),
                        props.get("gsd"), str(asset.get("proj:code") or props.get("proj:code") or props.get("proj:epsg") or "") or None,
                        license=item_license, license_status=status, trusted_provider=bool(self.config.get("trusted")),
                        access_status="public_download", estimated_size=asset.get("file:size"), content_type=asset.get("type", "").split(";")[0],
                        metadata={"stac_item_id": item["id"], "source_date": props.get("datetime"), "missingness": "unknown", "catalog_envelope_only": True, "data_origin_class": "public_remote_sensing", "fitness_for_purpose": "candidate metadata only; product-specific review required"},
                    ))
            return {"status": "available" if rows else "no_match", "candidates": rows}
        except (ConnectorError, ValueError, KeyError) as exc:
            return {"status": getattr(exc, "status", "invalid_metadata"), "candidates": [], "error_message": str(exc) if isinstance(exc, ConnectorError) else "Invalid STAC response"}

    def _collection_license(self, collection):
        cache = getattr(self, "_licenses", None)
        if cache is None:
            self._licenses = {}
            cache = self._licenses
        if collection in cache:
            return cache[collection]
        try:
            url = self.config["endpoint"].rstrip("/") + "/collections/" + collection
            with open_public(url, self.config["allowed_hosts"], interval=self.config.get("request_interval_seconds", 1)) as response:
                raw = response.read(256 * 1024 + 1)
            payload = json.loads(raw) if len(raw) <= 256 * 1024 else {}
            value = payload.get("license") or "unknown"
            self._licenses[collection] = value
            return value
        except (ConnectorError, ValueError):
            self._licenses[collection] = "unknown"
            return "unknown"

    def healthcheck(self):
        return {"connector_id": self.connector_id, "status": "degraded", "reason": "configured; live probe only on explicit search", "supported_datasets": list(self.config.get("collections", {}))}


class CopernicusStacConnector(GenericStacAdapter):
    connector_id = "copernicus_stac"
    display_name = "Copernicus Data Space STAC"

    def __init__(self, config=None):
        super().__init__(provider_config().get("copernicus_stac", {}) if config is None else config)

    def search(self, config):
        result = super().search(config)
        # Metadata search is available; asset hosting and collection licenses
        # are collection-specific and are not enabled for automatic fetch here.
        result["candidates"] = [replace(candidate, access_status="discover_only") for candidate in result.get("candidates", [])]
        return result


class NASACMRConnector(DataConnector):
    connector_id = "nasa_cmr"
    display_name = "NASA Earthdata CMR"
    provider = "NASA Earthdata CMR"
    authentication_type = "Earthdata Login for restricted granule downloads"
    data_types = ("rainfall", "temperature", "soil_moisture", "satellite_image", "dem")

    def __init__(self, config=None):
        self.config = provider_config().get("nasa_cmr", {}) if config is None else config

    def search(self, config):
        if not config.get("online", False):
            return {"status": "offline_discovery", "candidates": []}
        kind = config.get("data_type", "rainfall")
        short_name = config.get("short_name") or self.config.get("collections", {}).get(kind)
        params = {"page_size": min(max(int(config.get("limit", 5)), 1), 20), "include_has_granules": "true"}
        granules = bool(config.get("granules"))
        if granules:
            collection_id = config.get("collection_concept_id")
            if not collection_id:
                return {"status": "collection_required_for_granules", "candidates": []}
            params.pop("include_has_granules", None)
            params["collection_concept_id"] = str(collection_id)[:96]
        if short_name:
            params["short_name"] = short_name
        if config.get("keyword"):
            params["keyword"] = str(config["keyword"])[:120]
        if config.get("bbox"):
            DataConnector.validate_bounds({"bbox": list(config["bbox"]), "start": config.get("start") or "bounded", "end": config.get("end") or "bounded"})
            params["bounding_box"] = ",".join(map(str, config["bbox"]))
        if config.get("start") and config.get("end"):
            params["temporal"] = f"{config['start']}T00:00:00Z,{config['end']}T23:59:59Z"
        endpoint = self.config["endpoint"].rstrip("/") + ("/granules.json?" if granules else "/collections.json?") + urlencode(params)
        try:
            with open_public(endpoint, self.config["allowed_hosts"], headers={"Accept": "application/json"}, interval=self.config.get("request_interval_seconds", 1)) as response:
                payload = json.loads(response.read(2 * 1024 * 1024 + 1))
            entries = (payload.get("feed") or {}).get("entry", payload.get("items", []))
            rows = []
            for item in entries[:20]:
                title = item.get("dataset_id") or item.get("entry_title") or item.get("title") or "NASA CMR collection"
                concept = item.get("id") or item.get("concept_id") or item.get("concept-id") or title
                extent = item.get("boxes") or item.get("boxes_and_polygons") or []
                bbox = ()
                if extent and isinstance(extent[0], str):
                    try: bbox = tuple(float(value) for value in extent[0].split())
                    except ValueError: pass
                rows.append(DatasetCandidate(
                    str(concept), self.connector_id, self.provider, kind,
                    f"{self.config['endpoint'].rstrip('/')}/{('granules' if granules else 'collections')}/{concept}.json",
                    str(item.get("version_id") or item.get("version") or ""), (kind,), bbox,
                    tuple(item.get("time_start_end") or ()), None, None,
                    license=str(item.get("license") or "collection-specific terms"), license_status="unknown",
                    trusted_provider=True, access_status="discover_only",
                    metadata={"collection_title": title, "short_name": item.get("short_name"), "concept_id": concept,
                              "has_granules": item.get("has_granules"), "downloadable": item.get("downloadable"),
                              "result_level": "granule" if granules else "collection", "collection_concept_id": config.get("collection_concept_id"),
                              "data_origin_class": "public_remote_sensing", "fitness_for_purpose": "collection metadata only; product estimates do not replace project measurements", "auth_status": "auth_required_for_restricted_download"},
                ))
            return {"status": "available" if rows else "no_match", "candidates": rows}
        except (ConnectorError, ValueError, KeyError, TypeError) as exc:
            return {"status": getattr(exc, "status", "invalid_metadata"), "candidates": [], "error_message": str(exc) if isinstance(exc, ConnectorError) else "Invalid NASA CMR response"}

    def healthcheck(self):
        return {"connector_id": self.connector_id, "status": "degraded", "reason": "public metadata search; granule download/auth is separate", "supported_datasets": list(self.config.get("collections", {})), "authentication": "not required for search"}

    def fetch(self, candidate, **kwargs):
        from hydrolite.connectors.contracts import FetchedDataset
        return FetchedDataset("auth_required", candidate.as_dict(), error_message="CMR metadata is public; granule access is not verified as anonymous. Configure Earthdata Login through the supported user workflow.").as_dict()


class HydroSHEDSConnector(HttpFileConnector):
    connector_id = "hydrosheds"
    display_name = "HydroSHEDS official core products"

    def __init__(self, config=None):
        super().__init__(provider_config().get("hydrosheds", {}) if config is None else config)

    @staticmethod
    def tile_candidates(bbox):
        west, south, east, north = map(float, bbox)
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("Invalid WGS84 bbox")
        # The official 3-arc-second product uses 10x10 degree tiles; this returns
        # coordinate-derived candidates without guessing provider filenames.
        return [f"SW:{lon}:{lat}" for lon in range(int(west // 10 * 10), int((east - 1e-12) // 10 * 10) + 1, 10)
                for lat in range(int(south // 10 * 10), int((north - 1e-12) // 10 * 10) + 1, 10)]

    def search(self, config):
        if not config.get("online", False):
            return {"status": "offline_discovery", "candidates": []}
        bbox = config.get("bbox")
        if not bbox:
            return {"status": "spatial_extent_required", "candidates": []}
        tiles = self.tile_candidates(bbox)
        kind = config.get("data_type", "dem")
        product = self.config.get("products", {}).get(kind)
        if not product:
            page_by_type = {"hydrography": ("HydroRIVERS", "https://www.hydrosheds.org/products/hydrorivers"),
                            "conditioned_dem": ("HydroSHEDS conditioned DEM", "https://www.hydrosheds.org/hydrosheds-core-downloads")}
            if kind not in page_by_type:
                return {"status": "unsupported", "candidates": [], "tile_candidates": tiles}
            title, page = page_by_type[kind]
            candidate = DatasetCandidate(title, self.connector_id, self.config.get("provider", "HydroSHEDS"), kind,
                page, "official_catalog_page", (kind,), (-180.0, -90.0, 180.0, 90.0), (), None, "EPSG:4326",
                license="product-specific license review", license_status="unknown", trusted_provider=True,
                access_status="discover_only", metadata={"official_product_page": page, "tile_candidates": tiles,
                    "data_origin_class": "derived", "fitness_for_purpose": "discovery only; product extent/license/resolution require review"})
            return {"status": "available", "candidates": [candidate], "tile_candidates": tiles}
        # Product table is intentionally conservative: only official Asia 30s
        # files with a published size below the 50 MiB automatic ceiling qualify.
        region = product.get("regions", {}).get("asia")
        aoi_bbox = tuple(map(float, bbox))
        if not region or not _covers(tuple(region["bbox"]), aoi_bbox):
            return {"status": "approval_required", "candidates": [], "tile_candidates": tiles, "reason": "No verified small regional product covers this AOI"}
        href = self.config["endpoint"].rstrip("/") + "/" + product["collection"] + "/" + region["filename"]
        candidate = DatasetCandidate(
            f"hydrosheds-v1/{kind}/asia-30s", self.connector_id, self.config.get("provider", "HydroSHEDS"), kind,
            href, "v1.1-30s", (kind,), tuple(region["bbox"]), (), 900.0, "EPSG:4326",
            license=region["license"], license_status="known", trusted_provider=True,
            access_status="public_download", estimated_size=int(region["estimated_mb"] * 1_000_000), content_type="application/zip",
            metadata={"official_product_page": "https://www.hydrosheds.org/hydrosheds-core-downloads",
                      "official_license_url": "https://www.hydrosheds.org/products/hydrosheds",
                      "citation": "Lehner, Verdin & Jarvis (2008), DOI:10.1029/2008EO100001",
                      "resolution_arc_seconds": 30, "aoi_tile_candidates": tiles,
                      "data_origin_class": "derived", "fitness_for_purpose": "regional_hydrography_baseline; inspect resolution and extent"},
        )
        if candidate.estimated_size > 50 * 1024 * 1024:
            return {"status": "size_limit", "candidates": [], "tile_candidates": tiles}
        return {"status": "available", "candidates": [candidate], "tile_candidates": tiles}

    def fetch(self, candidate, **kwargs):
        return super().fetch(candidate, **kwargs)

    def healthcheck(self):
        return {"connector_id": self.connector_id, "display_name": self.display_name,
                "status": "degraded", "authentication_type": "none",
                "supported_datasets": list(self.config.get("data_types", [])),
                "reason": "official products configured; network probe only on explicit search"}


def _covers(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


class MeteorologicalConnector(DataConnector):
    connector_id = "meteorological"
    data_types = ("precipitation", "temperature", "pet", "et", "soil_moisture")

    def search(self, config):
        return {"status": "provider_not_configured", "candidates": []}

    def canonical_table(self, frame, dataset_type, metadata):
        from hydrolite.data_acquisition import canonical_online_table
        return canonical_online_table(frame, dataset_type, metadata)


class HydrologyObservationConnector(MeteorologicalConnector):
    connector_id = "hydrology_observations"
    data_types = ("streamflow_observed", "water_level_observed")

    def discover_stations(self, config):
        return {"status": "provider_not_configured", "stations": [], "fields": ["station_id", "variable", "timestamp", "flow", "stage", "provenance", "access_status"]}


class EnvironmentalMonitoringConnector(MeteorologicalConnector):
    connector_id = "environmental_monitoring"
    data_types = ("CODMn", "NH3-N", "TN", "TP", "DO")

    def healthcheck(self):
        return {**super().healthcheck(), "status": "unavailable", "access_status": "unavailable", "reason": "No verified public monitoring API configured"}


class RegulatoryDataConnector(MeteorologicalConnector):
    connector_id = "regulatory"
    data_types = ("emission_factors", "permits", "guidelines")

    def search(self, config):
        rows = []
        for entry in provider_config().get("regulatory", {}).get("references", []):
            if entry.get("data_type") == config.get("data_type"):
                rows.append(DatasetCandidate(**{**entry, "connector_id": self.connector_id, "access_status": "approval_required"}))
        return {"status": "approval_required" if rows else "provider_not_configured", "candidates": rows}


def gee_candidates(config):
    from hydrolite.gee_catalog.query import search_catalog
    kind = config.get("data_type", "dem")
    query = {"vegetation_index": "NDVI", "land_cover": "land cover", "rainfall": "precipitation", "soil_moisture": "soil moisture"}.get(kind, kind)
    results = search_catalog(query, result_limit=12)
    rows = []
    for row in results["records"]:
        rows.append(DatasetCandidate(
            row["asset_id"], "gee", row.get("provider") or "Earth Engine", kind,
            row.get("stac_url") or "", row.get("refresh_time") or "", (kind,),
            tuple(row.get("bbox") or []), tuple(row.get(key) or "" for key in ("start_date", "end_date")),
            row.get("nominal_scale_m"), row.get("projection"), license=row.get("license_text") or "unknown",
            # Catalog terms need dataset-level review; a URL alone is not redistribution permission.
            license_status="unknown", trusted_provider=True, access_status="authentication_required",
            metadata={"official_url": row.get("official_catalog_url"), "temporal_resolution": row.get("temporal_resolution"), "bands": row.get("bands", []), "catalog_only": True, "missingness": "unknown", "data_origin_class": "public_remote_sensing", "fitness_for_purpose": "catalog discovery only; compute/export auth remains separate"},
        ))
    return {"status": "available" if rows else "no_match", "candidates": rows, "compute_status": "authentication_required"}
