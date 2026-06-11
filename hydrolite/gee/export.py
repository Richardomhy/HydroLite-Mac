from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def export_to_drive_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {
        "status": "placeholder",
        "message": "GEE Drive export is not implemented in this skeleton.",
    }


def export_to_local_placeholder(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {
        "status": "placeholder",
        "message": "GEE local export is not implemented in this skeleton.",
    }


def write_gee_export_plan(path: str | Path, plan: dict[str, Any] | None = None) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = plan or {
        "status": "placeholder",
        "steps": [
            "Authenticate Earth Engine outside HydroLite.",
            "Select basin boundary and datasets.",
            "Create export tasks manually or through a future safe connector.",
        ],
    }
    output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return output_path
