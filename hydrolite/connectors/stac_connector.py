from __future__ import annotations

import importlib.util
from urllib.parse import urlparse

from hydrolite.connectors.base import DataConnector


WHITELIST = {"earth-search.aws.element84.com", "planetarycomputer.microsoft.com"}


class StacConnector(DataConnector):
    connector_id = "stac"
    display_name = "Public STAC"
    authentication_type = "none/public endpoint"

    def detect_dependencies(self):
        available = importlib.util.find_spec("pystac_client") is not None
        return {"available": available, "missing": [] if available else ["pystac-client"]}

    def list_supported_datasets(self):
        return ["Sentinel-2", "Landsat", "Copernicus DEM"]

    def search(self, config):
        self.validate_bounds(config)
        endpoint = config.get("endpoint", "")
        if urlparse(endpoint).hostname not in WHITELIST and not config.get("user_confirmed_endpoint"):
            raise ValueError("STAC endpoint is not whitelisted; explicit user confirmation is required.")
        return {"status": "search_plan", "endpoint": endpoint, "collection": config.get("collection"), "bbox": config["bbox"], "datetime": f"{config['start']}/{config['end']}", "download_execute": False}
