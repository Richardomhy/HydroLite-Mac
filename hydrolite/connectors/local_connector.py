from __future__ import annotations

from pathlib import Path
from hydrolite.connectors.base import DataConnector
from hydrolite.data_upload import inspect_uploaded_file


class LocalConnector(DataConnector):
    connector_id = "local"
    display_name = "Local files"

    def list_supported_datasets(self):
        return ["all registered upload types"]

    def search(self, config):
        path = Path(config["path"])
        return {"status": "passed" if path.exists() else "not_found", "results": [inspect_uploaded_file(path)] if path.is_file() else []}
