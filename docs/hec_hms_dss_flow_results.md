# HEC-HMS DSS Flow Results

HydroLite reads completed HEC-HMS 4.13 Simulation DSS results through the bundled Java/HEC-DSS classes. The verified demo contains 51 catalog pathnames, including 27 flow-related pathnames. Reading is timeout-bounded to 60 seconds and each pathname failure is retained independently.

## DSS Pathnames

A DSS pathname has six parts: `/A/B/C/D/E/F/`. HydroLite records all six parts. In the current result DSS, B identifies the HMS element, C identifies the parameter, E is the interval, and F identifies `RUN:hydrolite_run`. Dated D-parts are condensed only when they describe blocks of one regular series.

Flow classification distinguishes instantaneous `FLOW`, `OUTFLOW`, `INFLOW`, direct flow, baseflow and routed flow from average flow, cumulative flow, volume and unit-hydrograph patterns. A name containing `FLOW` is not automatically treated as an outlet hydrograph.

## Reading And Units

Timestamps come from the DSS start time plus its regular interval. Missing values remain missing. Original values, units and DSS type are retained. `CMS` and `M3/S` pass through unchanged; `CFS` and `FT3/S` use `1 ft3/s = 0.028316846592 m3/s`. Unknown units leave `flow_cms` empty and block quantitative comparison.

```bash
python -m hydrolite hms catalog-results output/hec_hms_project_rainfall_verified
python -m hydrolite hms read-flow-results output/hec_hms_project_rainfall_verified
python -m hydrolite hms extract-results output/hec_hms_project_rainfall_verified
```

Outputs are written under `output/hec_hms_results/`. Raw DSS files are never included in Git or the comparison bundle.

## Current Boundary

The small generated project has verified compute and result extraction, but the HEC-HMS workflow remains `partial`. Production-project adaptation and calibration are not complete.
