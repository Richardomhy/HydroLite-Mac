from __future__ import annotations

from hydrolite.connectors.local_connector import LocalConnector
from hydrolite.connectors.gee_connector import GeeConnector
from hydrolite.connectors.earthdata_connector import EarthdataConnector
from hydrolite.connectors.cds_connector import CdsConnector
from hydrolite.connectors.stac_connector import StacConnector


_CONNECTORS = {item.connector_id: item for item in (LocalConnector(), GeeConnector(), EarthdataConnector(), CdsConnector(), StacConnector())}


def list_connectors():
    return [connector.healthcheck() for connector in _CONNECTORS.values()]


def get_connector(connector_id: str):
    if connector_id not in _CONNECTORS:
        raise KeyError(f"Unknown connector: {connector_id}")
    return _CONNECTORS[connector_id]
