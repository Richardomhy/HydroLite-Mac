# HEC-HMS rainfall compute validation

After the compute gate passes, HydroLite can read the non-empty Simulation DSS, classify its 51 pathnames and extract the 27 flow pathnames. This result analysis does not change the rainfall gate and does not imply calibration; see `docs/hec_hms_hydrolite_comparison.md`.

The rainfall-verified project is an original minimal HydroLite-generated HEC-HMS 4.13 project under `output/hec_hms_project_rainfall_verified/`. It does not overwrite earlier generated projects or the copied official reference.

## Safety gate

`rainfall-compute` requires valid rainfall, regular interval, aligned control window, available DSS backend, non-empty DSS write, full read-back validation, a defined gage, one meteorologic method, every subbasin linked, valid run references, successful `Project.open`, and no fatal errors. Each HEC task is capped at 120 seconds and cleanup targets only its own process group.

Success requires a real `computeRun`, return code zero, no fatal log error, a non-empty result DSS, and at least one discovered simulated flow pathname. The result catalog classifies precipitation input, subbasin/reach/outlet flow, basin average, loss, excess precipitation, and unknown records. It does not perform deep DSS analytics.

## Manual review in HEC-HMS

Open `HydroLite_HMS_Project.hms`, then verify Shared Data precipitation gage `HydroLite_Precip`, the external DSS relative filename and pathname, `hydrolite_meteorologic` Weighted Gages assignments, `hydrolite_control` dates and interval, and `hydrolite_run` Basin/Precip/Control references. Review the simulation log and graph/table results before engineering use.

Common failures are an unavailable HEC-DSS backend, irregular rainfall, mismatched control dates, missing gage or subbasin mapping, invalid relative paths, HEC-HMS parse errors, timeout, or a result DSS without flow records.
