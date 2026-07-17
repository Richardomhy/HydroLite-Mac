# HEC-HMS File Format Calibration

## Method

HydroLite parses only the generic structure needed for calibration: component headers, names, metadata, block endings, inter-file references, and Run references. Unrecognized text remains in `raw_sections` or `unknown_lines`; the parser does not rewrite official files or claim to be a complete HEC-HMS parser.

The comparison command is:

```bash
python -m hydrolite hms compare-format \
  output/hec_hms_reference/reference_project \
  output/hec_hms_project
```

It writes JSON, XLSX, and Markdown reports under `output/hec_hms_reference/reports/`.

## Calibrated Rules

- Components are stored in the project root rather than custom `basin/`, `met/`, `control/`, and `run/` subdirectories.
- The `.hms` file registers Basin, Precipitation, and Control components with `Filename` or `FileName`.
- The simulation Run is stored in a project-named `.run` file; a `hydrolite_run.run` compatibility copy is also emitted for existing HydroLite tooling.
- Each component uses the correct header (`Project`, `Basin`, `Meteorology`, `Control`, or `Run`) and every block closes with `End:`.
- Run references use component names, not component file paths.
- Version, date/time, file separator, unit system, log, and DSS fields follow HEC-HMS 4.13 conventions.
- Basin downstream references are checked against generated elements.

## Generated Validation Project

```bash
python -m hydrolite hms calibrate-project \
  projects/qgis_workflow_project \
  output/hec_hms_project_verified
python -m hydrolite hms open-probe output/hec_hms_project_verified
python -m hydrolite hms compute-probe output/hec_hms_project_verified
```

The generated project must pass `Project.open` and expose a Run before calculation is considered. The compute gate additionally checks component references, fatal logs, project size, timeout, rainfall readiness, control period, time step, and basin topology.

The current calibrated project intentionally has no fabricated HEC-HMS precipitation store. It can pass `Project.open`, but compute remains skipped until rainfall is represented by a supported HEC-HMS precipitation method. HydroLite does not create a fake DSS file to bypass this requirement.

## Validation Levels

`generated_only`, `syntax_compared`, `project_opened`, `run_discovered`, `compute_attempted`, `compute_completed`, `compute_failed`, and `unavailable` are distinct states. `run_discovered` must never be described as simulation completion.

## DSS Boundary

This phase discovers DSS files and records path, size, modification time, empty status, likely role, and whether a process created or changed the file. DSS record/pathname reading remains planned.
# Precipitation calibration

The generated project now follows the observed Castro `.gage` and `.met` patterns: an external-DSS precipitation gage, a single `Weighted Gages` method, explicit weight `1.0` for each subbasin, relative DSS paths, and synchronized Control Specifications. See `hec_hms_precipitation_dss.md` for read-back checks.
