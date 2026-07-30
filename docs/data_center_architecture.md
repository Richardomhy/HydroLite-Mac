# Unified Data Center Architecture

The v0.7.0-dev data center is a `partial` workflow:

`workspace -> immutable raw upload -> inspection -> mapping -> quality -> standardized/derived -> lineage -> model input`

Raw files are copied once and made read-only. Transformations never overwrite them. CSV, XLSX, GeoJSON, ZIP Shapefile inspection and ASCII Grid checks have lightweight paths. GeoTIFF, NetCDF, HDF5 and advanced vector operations use optional dependencies or `qgis_process`.

Connectors only create bounded plans by default. Downloads require bbox, dates, explicit confirmation and `--execute`. Credentials remain outside the repository. Missing data remains missing and model-readiness reports explain the effect.
