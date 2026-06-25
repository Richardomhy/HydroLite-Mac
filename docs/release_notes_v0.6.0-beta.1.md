# HydroLite Studio v0.6.0-beta.1 Release Notes

- Version: `v0.6.0-beta.1`
- Release date: `2026-06-25`
- Base release: `v0.6.0-beta`
- Commit: to be recorded in `release/v0.6.0-beta.1/release_manifest.json`
- Tag: `v0.6.0-beta.1`
- GitHub: https://github.com/Richardomhy/HydroLite-Mac.git
- Streamlit Cloud: https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app

## Summary

HydroLite Studio v0.6.0-beta.1 is a patch release for the v0.6.0 beta line. It does not add model algorithms or large new modules. It packages the beta feedback loop, GitHub Issue templates, smoke test documents, post-release validation workflow, and release manifest updates.

## Patch Changes Since v0.6.0-beta

- Added GitHub Issue templates for bug reports, feature requests, beta feedback, and data template issues.
- Added a Streamlit `Beta 反馈` page.
- Added beta CLI commands:
  - `python -m hydrolite beta info`
  - `python -m hydrolite beta checklist`
  - `python -m hydrolite beta smoke-local`
- Added cloud smoke test documentation.
- Added local smoke test documentation.
- Added post-release validation documentation.
- Added beta feedback workflow documentation.
- Updated release package and manifest for the patch release.

## Difference From v0.6.0-beta

The modeling workflow, GEE/SWMM/OpenHydroNet behavior, project workflow, data templates, project wizard, tutorial, comparison, and report export remain unchanged. This patch only improves release verification and user feedback handling.

## Known Limitations

- GEE requires user authentication and a valid Earth Engine project for real data access.
- SWMM backends depend on the local or cloud runtime environment.
- OpenHydroNet support prepares input packages only; it does not train or run large-scale inference.
- Streamlit Cloud is best for demos and feedback. Full workflows are recommended locally.

## Test Result Summary

Final command results are recorded in `docs/v0.6.0_beta_1_checklist.md` and `release/v0.6.0-beta.1/release_manifest.json`.

Expected patch validation commands:

```bash
python -m hydrolite version
python -m hydrolite beta info
python -m hydrolite beta checklist
python -m hydrolite beta smoke-local
python -m hydrolite healthcheck
pytest -q
python -m streamlit run streamlit_app.py --server.headless true
```

## Safety Notes

- `data_raw/` remains read-only.
- Release packages exclude secrets, external repositories, model weights, checkpoints, and `data_raw`.
- Do not upload credentials, tokens, service account files, or sensitive project data in feedback issues.
