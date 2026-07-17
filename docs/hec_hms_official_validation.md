# HEC-HMS 4.13 Official Project Validation

## Purpose

HydroLite first validates the HEC-HMS scripting runtime with an installation-provided project, then uses that evidence to assess generated projects. This prevents a successful Java probe or a syntactically plausible file from being reported as a successful simulation.

## Reference Project

HEC-HMS 4.13 includes `samples.zip` under its application resources. HydroLite performs a bounded scan, selects the smallest suitable project, and copies it to `output/hec_hms_reference/reference_project/`. The installed archive is never modified and the copied sample remains ignored by Git.

The macOS package samples contain DSS v6 files. HEC-HMS reports that DSS v6 is unsupported on Unix/macOS, so HydroLite uses the package's own `migrate-to-dss-7` utility on the output copy only. This compatibility migration is recorded in the reference result.

## Official Jython Flow

```python
from hms.model import Project
from hms import Hms

project = Project.open("/absolute/path/project.hms")
project.computeRun("Run Name")
project.close()
Hms.shutdownEngine()
```

`reference-open` omits `computeRun`. It verifies a non-null project, discovers Run names, closes the project, and shuts down the engine. `reference-compute` is allowed only after that open gate succeeds and is limited to 120 seconds.

```bash
python -m hydrolite hms reference-scan
python -m hydrolite hms reference-info
python -m hydrolite hms reference-open
python -m hydrolite hms reference-compute
```

## Status Meanings

- `project_opened`: HEC-HMS opened and closed the project without a fatal structure error. This is not a simulation result.
- `compute_completed`: `computeRun` returned, the process exited normally, and no fatal log line was found.
- `compute_failed`: calculation was attempted but failed; inspect stdout, stderr, `.log`, and `.out` files.
- `skipped_*`: a prerequisite gate was not met, so no calculation was attempted.

## Reports

- `output/hec_hms_reference/reports/hec_hms_official_reference_report.md`
- `output/hec_hms_reference/reports/hec_hms_official_reference_result.json`
- `output/hec_hms_reference/reports/hec_hms_official_validation_summary.xlsx`

After every probe, check that no HEC-HMS Java process remains. For engineering review, open the copied or generated project manually in HEC-HMS 4.13 and inspect basin connectivity, meteorology, control period, units, parameters, and Run configuration.

## Current Boundary

This validation proves the official `Project.open / computeRun / close / shutdownEngine` route on the local installation. It does not add flood prediction, drought prediction, GUI automation, or deep DSS time-series analysis.
