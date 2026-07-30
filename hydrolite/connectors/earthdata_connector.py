from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from hydrolite.connectors.base import DataConnector


class EarthdataConnector(DataConnector):
    connector_id = "earthdata"
    display_name = "NASA Earthdata"
    authentication_type = "Earthdata Login"

    def detect_dependencies(self):
        available = importlib.util.find_spec("earthaccess") is not None
        return {"available": available, "missing": [] if available else ["earthaccess"]}

    def detect_authentication(self):
        present = bool(os.getenv("EARTHDATA_TOKEN") or (Path.home() / ".netrc").exists())
        return {"status": "detected" if present else "not_authenticated", "credentials_redacted": True}

    def list_supported_datasets(self):
        return ["ICESat2_ATL03", "ICESat2_ATL13", "ICESat2_ATL24", "GPM", "SMAP", "MODIS", "SRTM", "NASADEM"]

    def search(self, config):
        self.validate_bounds(config)
        limit = min(int(config.get("max_granules", 20)), 20)
        return {"status": "search_plan", "max_granules": limit, "bbox": config["bbox"], "start": config["start"], "end": config["end"], "download_execute": False}
