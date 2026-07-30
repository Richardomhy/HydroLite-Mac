#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-minimal}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="$ROOT/output/data_center"
mkdir -p "$OUTPUT"
LOG="$OUTPUT/data_center_setup.log"

{
  echo "HydroLite data center dependency setup"
  echo "mode=$MODE"
  echo "python=$(command -v python)"
  echo "CONDA_PREFIX=${CONDA_PREFIX:-}"
  echo "VIRTUAL_ENV=${VIRTUAL_ENV:-}"
  if [[ "$(command -v python)" == "/usr/bin/python"* ]]; then
    echo "Refusing to modify system Python. Activate the HydroLite conda/venv environment."
    exit 2
  fi
  case "$MODE" in
    minimal)
      packages=("openpyxl>=3.1" "python-dateutil>=2.8" "charset-normalizer>=3")
      ;;
    gis)
      packages=("shapely>=2" "pyproj>=3" "rasterio>=1.3" "geopandas>=0.14")
      ;;
    connectors)
      packages=("earthengine-api>=1" "earthaccess>=0.10" "cdsapi>=0.7" "pystac-client>=0.8" "fsspec>=2024")
      ;;
    all)
      packages=("openpyxl>=3.1" "python-dateutil>=2.8" "charset-normalizer>=3" "xarray>=2024" "netCDF4>=1.7" "h5py>=3.11" "shapely>=2" "pyproj>=3" "rasterio>=1.3" "geopandas>=0.14" "earthengine-api>=1" "earthaccess>=0.10" "cdsapi>=0.7" "pystac-client>=0.8" "fsspec>=2024")
      ;;
    *)
      echo "Usage: $0 [minimal|gis|connectors|all]"
      exit 2
      ;;
  esac
  printf 'packages=%s\n' "${packages[*]}"
  python -m pip install --disable-pip-version-check "${packages[@]}"
  python "$ROOT/scripts/diagnose_data_center_dependencies.py"
  echo "Setup complete. To undo newly installed optional packages, remove only packages listed above from this environment."
} 2>&1 | tee "$LOG"
