# HydroLite Studio v0.5.0-alpha Release Notes

Release date: 2026-06-12

## Version Name

HydroLite Studio v0.5.0-alpha

## Core Capabilities

- Project-centered HydroLite Studio Streamlit workbench.
- YAML scenario validation and batch execution.
- SCS-CN runoff generation, simplified unit hydrograph routing, and Muskingum channel routing.
- Muskingum parameter stability checks.
- Water balance checks and warning reporting.
- SWMM coupling through copied `working.inp` files.
- GEE data center for basin summaries and HydroLite input products when user authentication is configured.
- OpenHydroNet-ready input package generation.
- Scenario comparison and automatic Markdown/Excel/CSV reporting.
- Project export package for demos and handoff.

## New Features

- `python -m hydrolite version`
- `python -m hydrolite healthcheck`
- `hydrolite/__version__.py`
- HydroLite Studio sidebar version display.
- Release documentation set.
- `release/` package with manifest.

## Known Limitations

- This is not a full MIKE replacement.
- OpenHydroNet support prepares input packages only; it does not run real AI prediction.
- GEE requires a user Google Earth Engine account and project.
- SWMM execution may be limited on cloud environments by binary dependencies.
- Demo observed flow is synthetic/demo only.
- Parameter suggestions are heuristic and are not calibrated model parameters.

## Not Suitable For

- Regulatory engineering approval without independent review.
- Real-time emergency operations without production hardening.
- Large-scale AI training or inference.
- Replacing detailed 1D/2D hydraulic modeling software.

## Security Notes

- `data_raw/` is read-only for workflow runs.
- Secrets, credentials, `.streamlit/secrets.toml`, external repositories, and model weights are excluded from release checks.
- The OpenHydroNet external repository is not committed.

## Rollback Commit

Rollback to the stable pre-release workbench commit:

```text
869cb010b76a976810026e15fffbfd966ad67b15
```

## Test Summary

Release preparation verifies:

- `python -m hydrolite version`
- `python -m hydrolite healthcheck`
- project validate/batch/compare/export
- legacy validate/run/batch/compare
- OpenHydroNet input package generation
- `pytest -q`
- Streamlit startup
