from __future__ import annotations

from pathlib import Path
from typing import Any


class DataConnector:
    connector_id = "base"
    display_name = "Base"
    authentication_type = "none"

    def detect_dependencies(self) -> dict[str, Any]:
        return {"available": True, "missing": []}

    def detect_authentication(self) -> dict[str, Any]:
        return {"status": "not_required"}

    def list_supported_datasets(self) -> list[str]:
        return []

    def search(self, config: dict[str, Any]) -> dict[str, Any]:
        return {"status": "not_implemented", "results": []}

    def preview(self, config: dict[str, Any]) -> dict[str, Any]:
        return self.search(config)

    def estimate_download(self, config: dict[str, Any]) -> dict[str, Any]:
        return {"estimated_size_mb": None, "download_execute": False}

    def download(self, config: dict[str, Any], execute: bool = False) -> dict[str, Any]:
        return {"status": "dry_run" if not execute else "not_implemented", "download_execute": execute}

    def export_to_workspace(self, result: dict[str, Any], workspace_dir: str | Path) -> dict[str, Any]:
        return {"status": "not_executed", "workspace_dir": str(Path(workspace_dir))}

    def cancel(self, task_id: str) -> dict[str, Any]:
        return {"status": "not_running", "task_id": task_id}

    def healthcheck(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "display_name": self.display_name,
            "authentication_type": self.authentication_type,
            "dependencies": self.detect_dependencies(),
            "authentication": self.detect_authentication(),
            "download_execute_default": False,
            "supported_datasets": self.list_supported_datasets(),
        }

    @staticmethod
    def validate_bounds(config: dict[str, Any]) -> None:
        bbox = config.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError("A bounded bbox [west, south, east, north] is required.")
        if not config.get("start") or not config.get("end"):
            raise ValueError("A bounded start/end time range is required.")
