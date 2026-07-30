from __future__ import annotations

import importlib.util
import os

from hydrolite.connectors.base import DataConnector


class GeeConnector(DataConnector):
    connector_id = "gee"
    display_name = "Google Earth Engine"
    authentication_type = "Earth Engine local credentials"

    def detect_dependencies(self):
        return {"available": importlib.util.find_spec("ee") is not None, "missing": [] if importlib.util.find_spec("ee") else ["earthengine-api"]}

    def detect_authentication(self):
        project = os.getenv("GEE_PROJECT")
        if not self.detect_dependencies()["available"]:
            return {"status": "dependency_missing", "project_id_detected": bool(project), "project_id": project or ""}
        try:
            from hydrolite.gee.auth import get_gee_status
            status = get_gee_status()
            initialized = status.get("initialization", {}).get("status")
            return {"status": "available" if initialized == "available" else initialized or "unavailable", "project_id_detected": bool(project), "project_id": project or ""}
        except Exception as exc:
            return {"status": "unavailable", "project_id_detected": bool(project), "project_id": project or "", "error": str(exc)}

    def list_supported_datasets(self):
        return ["dem", "rainfall", "temperature", "evapotranspiration", "soil_moisture", "land_cover", "NDVI", "surface_water", "satellite_image"]

    def search(self, config):
        self.validate_bounds(config)
        return {"status": "metadata_plan", "dataset_type": config.get("dataset_type"), "bbox": config["bbox"], "start": config["start"], "end": config["end"], "download_execute": False}
