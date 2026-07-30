#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
import json
import os
import platform
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "data_center"
MODULES = {
    "pydantic": "pydantic", "pyarrow": "pyarrow", "openpyxl": "openpyxl", "python-dateutil": "dateutil",
    "charset-normalizer": "charset_normalizer", "xarray": "xarray", "netCDF4": "netCDF4", "h5py": "h5py",
    "cftime": "cftime", "scipy": "scipy", "shapely": "shapely", "pyproj": "pyproj",
    "rasterio": "rasterio", "geopandas": "geopandas", "fiona": "fiona", "earthengine-api": "ee",
    "earthaccess": "earthaccess", "cdsapi": "cdsapi", "pystac-client": "pystac_client",
    "requests": "requests", "fsspec": "fsspec",
}


def diagnose() -> dict:
    packages = []
    for package, module in MODULES.items():
        try:
            imported = import_module(module)
            packages.append({"package": package, "module": module, "available": True, "version": getattr(imported, "__version__", "unknown"), "error": ""})
        except Exception as exc:
            packages.append({"package": package, "module": module, "available": False, "version": "", "error": f"{type(exc).__name__}: {exc}"})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "conda_prefix": os.getenv("CONDA_PREFIX", ""),
        "virtual_env": os.getenv("VIRTUAL_ENV", ""),
        "minimal_ready": all(next(row for row in packages if row["package"] == name)["available"] for name in ("openpyxl", "python-dateutil", "charset-normalizer")),
        "packages": packages,
        "fallbacks": {
            "tables": "pandas/openpyxl",
            "geojson": "Python json lightweight backend",
            "zip_shapefile": "stdlib zip validation",
            "ascii_grid": "NumPy lightweight backend",
            "heavy_gis": "qgis_process or optional GIS extra",
            "external_connectors": "status and dry-run remain available without optional packages",
        },
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = diagnose()
    json_path = OUTPUT / "dependency_diagnosis.json"
    md_path = OUTPUT / "dependency_diagnosis.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Data Center Dependency Diagnosis", "", f"- Python: `{result['python_executable']}`", f"- Conda: `{result['conda_prefix'] or 'not detected'}`", f"- Minimal ready: `{result['minimal_ready']}`", "", "| Package | Available | Version |", "|---|---:|---|"]
    lines.extend(f"| {row['package']} | {row['available']} | {row['version']} |" for row in result["packages"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed" if result["minimal_ready"] else "failed", "json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0 if result["minimal_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
