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
                        metadata={"stac_item_id": item["id"], "source_date": props.get("datetime"), "missingness": "unknown", "catalog_envelope_only": True},
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
            metadata={"official_url": row.get("official_catalog_url"), "temporal_resolution": row.get("temporal_resolution"), "bands": row.get("bands", []), "catalog_only": True, "missingness": "unknown"},
        ))
    return {"status": "available" if rows else "no_match", "candidates": rows, "compute_status": "authentication_required"}
