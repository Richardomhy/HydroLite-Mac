from __future__ import annotations

from pathlib import Path
from typing import Any


def load_basin_boundary(path: str | Path) -> dict[str, Any]:
    boundary_path = Path(path).expanduser()
    return {
        "path": str(boundary_path),
        "exists": boundary_path.exists(),
        "suffix": boundary_path.suffix.lower(),
        "status": "placeholder_loaded" if boundary_path.exists() else "missing",
    }


def summarize_basin_placeholder(boundary_path: str | Path) -> dict[str, Any]:
    loaded = load_basin_boundary(boundary_path)
    return {
        **loaded,
        "message": "Basin geometry parsing is a future step; this placeholder only checks file presence.",
    }
