from __future__ import annotations

from hydrolite.connectors.local_connector import LocalConnector
from hydrolite.connectors.gee_connector import GeeConnector
from hydrolite.connectors.earthdata_connector import EarthdataConnector
from hydrolite.connectors.cds_connector import CdsConnector
from hydrolite.connectors.stac_connector import StacConnector


_CONNECTORS = {item.connector_id: item for item in (LocalConnector(), GeeConnector(), EarthdataConnector(), CdsConnector(), StacConnector())}


def list_connectors():
    return DataConnectorRegistry().health()


def get_connector(connector_id: str):
    if connector_id in _CONNECTORS:
        return _CONNECTORS[connector_id]
    connector = DataConnectorRegistry().connectors.get(connector_id)
    if connector is None:
        raise KeyError(f"Unknown connector: {connector_id}")
    return connector


class DataConnectorRegistry:
    """Acquisition facade retains the existing connector IDs and legacy plan APIs."""
    def __init__(self, connectors=None):
        from hydrolite.connectors.public import (HttpFileConnector, GenericStacAdapter, CopernicusStacConnector,
            NASACMRConnector, HydroSHEDSConnector, MeteorologicalConnector, HydrologyObservationConnector,
            EnvironmentalMonitoringConnector, RegulatoryDataConnector)
        defaults = [*_CONNECTORS.values(), HttpFileConnector(), GenericStacAdapter(), CopernicusStacConnector(),
                    NASACMRConnector(), HydroSHEDSConnector(), MeteorologicalConnector(),
                    HydrologyObservationConnector(), EnvironmentalMonitoringConnector(), RegulatoryDataConnector()]
        self.connectors = {item.connector_id: item for item in (defaults if connectors is None else connectors)}

    def register(self, connector):
        if connector.connector_id in self.connectors:
            raise ValueError("Connector already registered")
        self.connectors[connector.connector_id] = connector

    def list(self):
        return list(self.connectors)

    def capabilities(self):
        return {key: list(item.data_types or item.list_supported_datasets()) for key, item in self.connectors.items()}

    def health(self):
        profiles = provider_profiles()
        rows = []
        for key, item in self.connectors.items():
            try:
                if key == "gee":
                    from hydrolite.gee_catalog.loader import inspect_catalog_availability
                    result = {"connector_id": key, "status": "degraded", "catalog": inspect_catalog_availability(), "compute_status": "authentication_required", "note": "Live compute not probed; catalog independent"}
                elif key in {"meteorological", "hydrology_observations", "regulatory"}:
                    result = {"connector_id": key, "status": "unavailable", "reason": "provider_not_configured"}
                else:
                    result = item.healthcheck()
                    result.setdefault("status", "healthy" if key == "local" else "degraded")
                result.setdefault("download_execute_default", False)
                profile = profiles.get("earth_engine" if key == "gee" else key)
                if profile:
                    result["provider_profile"] = profile
                rows.append(result)
            except Exception:
                rows.append({"connector_id": key, "status": "unavailable", "reason": "healthcheck_failed"})
        return rows

    def search(self, connector_id, config):
        if connector_id == "gee":
            from hydrolite.connectors.public import gee_candidates
            return gee_candidates(config)
        if connector_id not in self.connectors:
            return {"status": "unsupported", "candidates": []}
        try:
            result = self.connectors[connector_id].search(config)
            result.setdefault("candidates", [])
            failure_class = classify_provider_failure(result.get("status"))
            if failure_class:
                result["provider_failure_class"] = failure_class
            return result
        except Exception:
            return {"status": "online_source_unavailable", "candidates": [], "error_message": "Connector search failed; check bounded query/provider configuration"}

    def recommend(self, requirement, config=None):
        from hydrolite.data_requirement_resolver import rank_candidate
        request = {"data_type": requirement.data_type, "bbox": requirement.spatial_extent, **(config or {})}
        if requirement.temporal_extent:
            request.update(start=requirement.temporal_extent[0], end=requirement.temporal_extent[1])
        rows, searches = [], []
        configured = tuple(requirement.preferred_connectors) or source_priority_for(requirement.data_type)
        for provider_rank, key in enumerate(configured or ("gee", "http", "stac")):
            result = self.search(key, request)
            searches.append({"connector_id": key, "status": result["status"]})
            for item in result["candidates"]:
                ranked = rank_candidate(requirement, item)
                ranked["selection_reason"] = _selection_explanation(requirement, item, ranked)
                rows.append({"candidate": item.as_dict(), **ranked, "provider_rank": provider_rank})
            if any(row["eligible"] and row["candidate"].get("access_status") == "public_download" for row in rows):
                break
        return {"candidates": sorted(rows, key=lambda item: (bool(item["eligible"]), item["score"], -item["provider_rank"]), reverse=True), "searches": searches}

    def fetch(self, candidate, **kwargs):
        from hydrolite.connectors.contracts import DatasetCandidate, FetchedDataset
        candidate = DatasetCandidate(**candidate) if isinstance(candidate, dict) else candidate
        item = self.connectors.get(candidate.connector_id)
        if candidate.connector_id == "gee":
            return FetchedDataset("authentication_required", candidate.as_dict(), error_message="Catalog metadata is not an exported dataset; use existing GEE compute workflow").as_dict()
        return item.fetch(candidate, **kwargs) if item else FetchedDataset("unsupported", candidate.as_dict()).as_dict()


def source_priority_for(data_type):
    """Read the compact source matrix; local and cache are resolved before this list."""
    import yaml
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "config/connectors/data_source_matrix.yaml"
    try:
        matrix = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ()
    result = []
    aliases = {"rainfall_observed": "rainfall", "rainfall_forecast": "rainfall", "land_use": "land_cover", "observed_streamflow": "streamflow_observed"}
    lookup = aliases.get(data_type, data_type)
    for scenario in matrix.get("matrix", {}).values():
        for kind, values in scenario.items():
            if kind == lookup:
                result.extend(value for value in values if value not in {"local", "cache", "project_user", "approval_registry"})
    connector_ids = {"earth_engine": "gee"}
    return tuple(dict.fromkeys(connector_ids.get(item, item) for item in result))


def provider_profiles():
    import yaml
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "config/connectors/data_source_matrix.yaml"
    try:
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("providers", {})
    except (OSError, yaml.YAMLError):
        return {}


def classify_provider_failure(status):
    if status in {None, "available", "offline_discovery", "no_match"}:
        return "dataset_not_found" if status == "no_match" else None
    aliases = {"proxy_blocked": "security_blocked", "approval_required": "size_limit",
               "authentication_required": "auth_required", "license_unknown": "license_restricted",
               "license_restricted": "license_restricted", "unsupported_format": "unsupported",
               "configuration_error": "security_blocked", "unsafe_url": "security_blocked",
               "dataset_not_found": "dataset_not_found"}
    known = {"dns_failure", "non_public_resolution", "tls_failure", "remote_unavailable", "rate_limited",
             "auth_required", "license_restricted", "dataset_not_found", "size_limit", "unsupported", "security_blocked"}
    value = aliases.get(status, status)
    return value if value in known else ("unsupported" if value in {"unsupported", "provider_not_configured"} else None)


def _selection_explanation(requirement, candidate, ranked):
    if not ranked["eligible"]:
        failed = [key for key, value in ranked["quality"].items() if key != "missingness" and not value]
        return "Candidate not selected; failed suitability checks: " + ", ".join(failed)
    reasons = ["covers requested AOI", "matches requested variable"]
    if requirement.temporal_extent:
        reasons.append("covers requested time range")
    if requirement.minimum_resolution is not None:
        reasons.append(f"resolution {candidate.resolution} m satisfies maximum {requirement.minimum_resolution} m")
    reasons.extend(("trusted provider", "license metadata recorded", "download size within provider limit"))
    return "; ".join(reasons)
