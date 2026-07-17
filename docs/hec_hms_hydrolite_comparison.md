# HEC-HMS And HydroLite Comparison

This workflow compares two completed simulations of the same event. It is event diagnostics, not rainfall forecasting or a flood-warning system.

## Outlet Selection

The HMS outlet is selected from Basin topology in this order: explicit terminal sink/outlet, terminal reach, HydroLite terminal-reach mapping, manifest declaration, then an explicit user choice. Peak magnitude is never a selection rule. Multiple candidates block the main quantitative comparison.

The verified demo selects the terminal HMS junction `Outlet` and its instantaneous `FLOW` series. It maps to the unique terminal HydroLite reach through project topology.

## Alignment And Metrics

The default method is exact timestamp matching. The report records original and aligned counts, unmatched records, intervals, time window and timezone assumptions. No interpolation or missing-value filling is used. Optional resampling is allowed only with known time bases, units and an explicit aggregation rule.

Event metrics include peak flow/time, time to peak, volume by timestamp-aware trapezoidal integration, centroid time, rising/recession duration and duration above diagnostic 50/75/90 percent-of-peak thresholds. These relative thresholds are not statutory warning levels.

Model metrics reuse `hydrolite.metrics`: RMSE, MAE, PBIAS, NSE, KGE and R2. HEC-HMS is documented as the reference series for these comparison statistics; this does not imply it is observed truth.

```bash
python -m hydrolite hms compare-hydrolite output/hec_hms_project_rainfall_verified projects/qgis_workflow_project
python -m hydrolite hms validate-comparison output/hec_hms_comparison
```

Outputs include aligned and source CSVs, two Excel workbooks, six charts, a Markdown report and a bundle. The bundle excludes DSS, `data_raw`, official samples, secrets, external repositories and model weights.

## Interpretation

Large peak, volume or timing differences indicate different model structures and parameterization. They are not evidence that either model is calibrated. Calibration and flood forecasting remain planned work.
