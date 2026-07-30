#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "drought_model" / "environment"
PACKAGES = (
    ("numpy", "numpy"), ("pandas", "pandas"), ("scipy", "scipy"), ("xarray", "xarray"),
    ("netCDF4", "netCDF4"), ("h5py", "h5py"), ("cftime", "cftime"),
    ("scikit-learn", "sklearn"), ("joblib", "joblib"), ("pyproj", "pyproj"),
    ("shapely", "shapely"), ("cdsapi", "cdsapi"), ("earthaccess", "earthaccess"),
    ("pystac-client", "pystac_client"), ("fsspec", "fsspec"),
    ("rasterio", "rasterio"), ("geopandas", "geopandas"),
)


def diagnose() -> dict:
    packages = []
    for package, module in PACKAGES:
        available = importlib.util.find_spec(module) is not None
        try: version = importlib.metadata.version(package) if available else None
        except importlib.metadata.PackageNotFoundError: version = None
        packages.append({"package": package, "available": available, "version": version})
    conda_environment = os.getenv("CONDA_DEFAULT_ENV")
    result = {
        "status": "available" if all(row["available"] for row in packages[:15]) else "degraded",
        "python_version": platform.python_version(),
        "python_executable_name": Path(sys.executable).name,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "conda_environment": conda_environment,
        "is_conda_base": conda_environment == "base",
        "packages": packages,
        "credentials_recorded": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "dependency_diagnosis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# HydroLite science environment diagnosis", "",
        f"- status: `{result['status']}`", f"- Python: `{result['python_version']}`",
        f"- executable: `{result['python_executable_name']}`",
        f"- Conda environment: `{conda_environment or 'none'}`",
        f"- machine: `{result['machine']}`", "",
        "| package | available | version |", "|---|---:|---|",
        *[f"| {row['package']} | {row['available']} | {row['version'] or '-'} |" for row in packages],
        "", "No credentials or absolute user paths are written to these records.",
    ]
    (OUTPUT / "dependency_diagnosis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside-env", action="store_true")
    args = parser.parse_args()
    if not args.inside_env and shutil.which("conda"):
        environments = json.loads(subprocess.run(["conda", "env", "list", "--json"], capture_output=True, text=True, check=True).stdout)["envs"]
        target = next((path for path in environments if Path(path).name == "hydrolite-science"), None)
        if target:
            completed = subprocess.run(["conda", "run", "-n", "hydrolite-science", "python", str(Path(__file__).resolve()), "--inside-env"])
            return completed.returncode
    result = diagnose()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"available", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
