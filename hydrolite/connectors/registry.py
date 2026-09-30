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
        from hydrolite.connectors.public import HttpFileConnector, GenericStacAdapter, MeteorologicalConnector, HydrologyObservationConnector, EnvironmentalMonitoringConnector, RegulatoryDataConnector
        defaults = [*_CONNECTORS.values(), HttpFileConnector(), GenericStacAdapter(), MeteorologicalConnector(), HydrologyObservationConnector(), EnvironmentalMonitoringConnector(), RegulatoryDataConnector()]
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
            return result
        except Exception:
            return {"status": "online_source_unavailable", "candidates": [], "error_message": "Connector search failed; check bounded query/provider configuration"}

    def recommend(self, requirement, config=None):
        from hydrolite.data_requirement_resolver import rank_candidate
        request = {"data_type": requirement.data_type, "bbox": requirement.spatial_extent, **(config or {})}
        if requirement.temporal_extent:
            request.update(start=requirement.temporal_extent[0], end=requirement.temporal_extent[1])
        rows, searches = [], []
        for key in requirement.preferred_connectors or ("gee", "http", "stac"):
            result = self.search(key, request)
            searches.append({"connector_id": key, "status": result["status"]})
            rows.extend({"candidate": item.as_dict(), **rank_candidate(requirement, item)} for item in result["candidates"])
        return {"candidates": sorted(rows, key=lambda item: item["score"], reverse=True), "searches": searches}

    def fetch(self, candidate, **kwargs):
        from hydrolite.connectors.contracts import DatasetCandidate, FetchedDataset
        candidate = DatasetCandidate(**candidate) if isinstance(candidate, dict) else candidate
        item = self.connectors.get(candidate.connector_id)
        if candidate.connector_id == "gee":
            return FetchedDataset("authentication_required", candidate.as_dict(), error_message="Catalog metadata is not an exported dataset; use existing GEE compute workflow").as_dict()
        return item.fetch(candidate, **kwargs) if item else FetchedDataset("unsupported", candidate.as_dict()).as_dict()
