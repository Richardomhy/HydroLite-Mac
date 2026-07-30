from __future__ import annotations

import importlib.util
from pathlib import Path

from hydrolite.connectors.base import DataConnector


class CdsConnector(DataConnector):
    connector_id = "cds"
    display_name = "Copernicus Climate Data Store"
    authentication_type = ".cdsapirc"

    def detect_dependencies(self):
        available = importlib.util.find_spec("cdsapi") is not None
        return {"available": available, "missing": [] if available else ["cdsapi"]}

    def detect_authentication(self):
        return {"status": "detected" if (Path.home() / ".cdsapirc").exists() else "not_authenticated", "credentials_redacted": True}

    def list_supported_datasets(self):
        return ["ERA5", "ERA5-Land", "seasonal_forecast"]

    def search(self, config):
        self.validate_bounds(config)
        variables = config.get("variables") or []
        if not variables:
            raise ValueError("At least one CDS variable is required.")
        return {"status": "request_plan", "dataset": config.get("dataset", "reanalysis-era5-land"), "variables": variables, "bbox": config["bbox"], "start": config["start"], "end": config["end"], "format": config.get("format", "netcdf"), "download_execute": False}
