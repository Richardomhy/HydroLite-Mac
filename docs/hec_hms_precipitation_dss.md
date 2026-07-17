# HEC-HMS precipitation DSS

The precipitation DSS is an input data source; the Simulation DSS is the completed-run result source. Flow-result pathname classification and reading are documented separately in `docs/hec_hms_dss_flow_results.md`.

HydroLite rainfall CSV is a human-readable input table. HEC-HMS 4.13 does not treat a renamed CSV as a DSS database: the data must be written through a verified HEC-DSS API, cataloged, and read back before computation.

## Verified data chain

1. Read `projects/qgis_workflow_project/data/rainfall.csv` and standardize it to `timestamp` and `precipitation_increment_mm`.
2. Require parseable, increasing, unique timestamps, a regular interval, finite non-negative rainfall, and preserved rainfall total.
3. Write a `PER-CUM` record in `MM` with the HEC-HMS 4.13 bundled Java/Jython HEC-DSS classes.
4. Read the record back and compare pathname readability, count, start/end, interval, units, type, total, maximum, and missing values.
5. Define precipitation gage `HydroLite_Precip` with relative DSS file `data/hydrolite_precipitation.dss`.
6. Use the official-sample pattern `Weighted Gages`; the single recording gage has weight `1.0` for every generated subbasin.
7. Synchronize Control Specifications to the rainfall window and run the rainfall gate before `computeRun`.

The generated pathname is a complete six-part HEC-DSS pathname with `PRECIP-INC`, a blank D-part, the actual regular interval, and `OBS`. HEC-DSS may catalog dated D-parts internally; successful `get()` read-back is authoritative because `recordExists()` is not reliable for this blank-D-part spanning query.

## Commands

```bash
python -m hydrolite hms dss-backends
python -m hydrolite hms normalize-rainfall projects/qgis_workflow_project
python -m hydrolite hms create-rainfall-project projects/qgis_workflow_project output/hec_hms_project_rainfall_verified
python -m hydrolite hms rainfall-open-probe output/hec_hms_project_rainfall_verified
python -m hydrolite hms rainfall-gate output/hec_hms_project_rainfall_verified
python -m hydrolite hms rainfall-compute output/hec_hms_project_rainfall_verified
```

If the verified DSS backend is unavailable, the write and compute stages are skipped or failed clearly; no empty or unrelated DSS file is accepted as success.
