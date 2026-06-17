# HydroLite Studio v0.6.0-beta Release Notes

- Version: `v0.6.0-beta`
- Release date: `2026-06-17`
- GitHub: https://github.com/Richardomhy/HydroLite-Mac.git
- Streamlit Cloud: https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app

## Summary

HydroLite Studio v0.6.0-beta freezes the first beta release of the project-centered HydroLite workbench. Compared with `v0.5.0-alpha.2`, this release focuses on usability, project packaging, data preparation, guided onboarding, and report delivery.

## New Since v0.5.0-alpha.2

- Project workflow for project-local cases, configs, outputs, reports, and package export.
- Streamlit professional workbench with project-centered navigation.
- Project wizard for creating projects without hand-editing YAML.
- Real-project data templates for rainfall, subbasins, reaches, observed streamflow, SWMM inflow mapping, and GEE basin boundaries.
- Data template validation CLI and Streamlit page.
- Guided tutorial and demo mode.
- One-click Markdown, Word, HTML, PDF fallback, and report bundle export.
- GEE data center and HydroLite-ready input products.
- SWMM coupling, result extraction, and backend fallback.
- OpenHydroNet-ready input package generation.
- Observed streamflow import and model evaluation.

## Feature Matrix

| Area | Status |
| --- | --- |
| Project workflow | Beta ready |
| Streamlit workbench | Beta ready |
| Project wizard | Beta ready |
| Data templates | Beta ready |
| Data template validation | Beta ready |
| Tutorial and Demo mode | Beta ready |
| Report export | Beta ready with PDF fallback |
| GEE data center | Optional backend, graceful fallback |
| SWMM coupling | Optional backend, graceful fallback |
| OpenHydroNet-ready input package | Input preparation only |
| Observed streamflow evaluation | Beta ready |

## Verified Functions

- `python -m hydrolite version`
- `python -m hydrolite healthcheck`
- `python -m hydrolite templates ...`
- `python -m hydrolite wizard ...`
- `python -m hydrolite tutorial ...`
- `python -m hydrolite project ...`
- `python -m hydrolite report project ...`
- `python -m hydrolite validate/run/batch/compare ...`
- `pytest -q`
- Streamlit startup check

## Known Limitations

- This beta is not a full MIKE, SWMM, SWAT+, ANUGA, or OpenHydroNet replacement.
- GEE requires user authentication and a valid Google Cloud / Earth Engine project for real data access.
- SWMM backends can fail on some macOS binary environments; HydroLite uses graceful fallback and external solver support.
- OpenHydroNet integration prepares input packages and diagnostics only; it does not train or run large inference.
- PDF export depends on an optional PDF backend; otherwise a clear fallback note is generated.

## Not Suitable For

- Regulatory-grade hydraulic certification without professional review.
- Large-scale AI model training or forecasting.
- Direct editing of original `data_raw` datasets.
- Secret, credential, or model-weight storage.

## Safety Notes

- `data_raw/` remains a read-only raw-data area.
- Secrets, service accounts, API keys, external repositories, checkpoints, and model weights are excluded.
- Release packages exclude `external/`, `data_raw/`, credentials, and model artifacts.

## Rollback

Use the previous stable alpha tag if needed:

```bash
git checkout v0.5.0-alpha.2
```

## Test Summary

The release checklist records the final command results. The release manifest records the final git commit and tag.

## Git Commit

Final beta commit is recorded in `release/v0.6.0-beta/release_manifest.json`.
