from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_openhydronet_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("OpenHydroNet config root must be a mapping.")
    return data


def validate_openhydronet_config(config: dict[str, Any]) -> dict[str, Any]:
    required = [
        "enabled",
        "openhydronet_home",
        "mode",
        "basin_id",
        "gauge_id",
        "input",
        "output",
        "forecast",
    ]
    missing = [key for key in required if key not in config]
    adapter = config.get("input_adapter") or {}
    adapter_missing: list[str] = []
    if adapter.get("enabled", False):
        adapter_required = [
            "basin_id",
            "gauge_id",
            "gee_basin_summary",
            "gee_rainfall_csv",
            "gee_parameter_suggestions",
            "hydrolite_result_flow",
            "output_folder",
        ]
        adapter_missing = [key for key in adapter_required if not adapter.get(key)]
    status = "failed" if missing else "passed"
    if adapter_missing:
        status = "failed"
    return {
        "status": status,
        "missing": missing,
        "adapter_missing": adapter_missing,
        "message": "Configuration is structurally valid."
        if not missing and not adapter_missing
        else f"Missing keys: {missing}; missing input_adapter keys: {adapter_missing}",
    }
