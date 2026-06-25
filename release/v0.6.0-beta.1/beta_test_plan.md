# HydroLite Studio v0.6.0-beta Beta Test Plan

## Test Goals

- Verify that v0.6.0-beta can be installed, started, and used as a project-centered workbench.
- Confirm that project wizard, data templates, tutorial mode, report export, and legacy workflows remain functional.
- Confirm that release packages do not include secrets, external repositories, model weights, checkpoints, or `data_raw`.

## Test Environment

- macOS local environment.
- Python command: `python -m hydrolite ...`.
- Streamlit command: `python -m streamlit run streamlit_app.py --server.headless true`.
- Optional external services are allowed to fail gracefully.

## Test Flow

1. Check version and healthcheck.
2. Export and validate data templates.
3. Validate and preview project wizard template.
4. Run tutorial checklist and summary.
5. Validate, batch, compare, report, and export `projects/demo_project`.
6. Run legacy `cases/` workflow.
7. Run full pytest.
8. Start Streamlit briefly and stop it.
9. Inspect release package.

## Functional Checklist

| Area | Command / Page | Expected |
| --- | --- | --- |
| Version | `python -m hydrolite version` | `0.6.0-beta` |
| Healthcheck | `python -m hydrolite healthcheck` | completes |
| Data templates | `templates list/export-all/validate/summary` | completes |
| Project wizard | `wizard validate/preview` | completes |
| Tutorial | `tutorial list/checklist/summary` | completes |
| Project workflow | `project validate/batch/compare/export` | completes |
| Report export | `report project` | completes |
| Legacy workflow | `validate/run/batch/compare` | completes |
| Tests | `pytest -q` | passes |
| Streamlit | startup command | app starts |

## Data Template Tests

- Verify required fields.
- Verify numeric and datetime parsing.
- Verify GeoJSON parseability.
- Verify `templates_export/` is ignored.

## Project Wizard Tests

- Validate basic template.
- Preview project.
- Ensure project wizard page imports.

## Report Export Tests

- Generate Markdown, Word, HTML, PDF fallback, and report bundle.
- Ensure generated reports are ignored under `projects/*/reports/`.

## Online Version Tests

- Open Streamlit Cloud app.
- Navigate to tutorial, data templates, project wizard, comparison, and reports.
- Confirm optional backends fail gracefully.

## Local Version Tests

- Run full command matrix.
- Check generated project outputs.
- Check release package.

## Issue Log

| ID | Area | Severity | Steps | Expected | Actual | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BETA-001 |  |  |  |  |  |  |
