#!/bin/sh
set -eu

ENV_NAME="${HYDROLITE_SCIENCE_ENV:-hydrolite-science}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
OUTPUT="$ROOT/output/drought_model/environment"
mkdir -p "$OUTPUT"

if ! command -v conda >/dev/null 2>&1; then
  printf '%s\n' "conda is required to create the isolated $ENV_NAME environment." >&2
  exit 1
fi

if ! conda env list --json | TARGET_ENV="$ENV_NAME" python -c 'import json,sys,os; name=os.environ["TARGET_ENV"]; sys.exit(0 if any(path.rstrip("/").endswith("/"+name) for path in json.load(sys.stdin)["envs"]) else 1)' 2>/dev/null; then
  conda create -n "$ENV_NAME" python=3.12 -y
fi

conda install -n "$ENV_NAME" -y \
  numpy pandas scipy xarray netcdf4 h5py cftime scikit-learn joblib \
  pyproj shapely fsspec matplotlib openpyxl pyyaml
conda run -n "$ENV_NAME" python -m pip install --disable-pip-version-check \
  cdsapi earthaccess pystac-client

# GIS readers are optional. A failed install leaves qgis_process and the
# lightweight table model available.
conda install -n "$ENV_NAME" -y rasterio geopandas >"$OUTPUT/optional_gis_install.log" 2>&1 || true
conda run -n "$ENV_NAME" python -m pip install --no-deps -e "$ROOT"

cat >"$OUTPUT/conda_environment.yml" <<EOF
name: $ENV_NAME
channels:
  - conda-forge
dependencies:
  - python=3.12
  - numpy
  - pandas
  - scipy
  - xarray
  - netcdf4
  - h5py
  - cftime
  - scikit-learn
  - joblib
  - pyproj
  - shapely
  - fsspec
  - matplotlib
  - openpyxl
  - pyyaml
  - pip
  - pip:
      - cdsapi
      - earthaccess
      - pystac-client
EOF
conda run -n "$ENV_NAME" python -m pip list --format=freeze \
  | sed '/ @ file:/d;/^-e /d' >"$OUTPUT/requirements_lock.txt"
conda run -n "$ENV_NAME" python "$ROOT/scripts/diagnose_hydrolite_science_env.py" --inside-env
printf '%s\n' "HydroLite science environment ready: $ENV_NAME"
