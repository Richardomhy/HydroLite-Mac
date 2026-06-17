# HydroLite Studio Report Export

HydroLite Studio v0.6.0-dev includes a one-click report export workflow for project results. It converts existing project outputs into Markdown, Word, HTML, optional PDF, and a safe report bundle.

## What It Generates

For a project such as `projects/demo_project`, report files are written to:

```bash
projects/demo_project/reports/
```

Generated files:

- `project_report.md`: readable Markdown report.
- `project_report.docx`: editable Word report.
- `project_report.html`: browser-viewable report with embedded charts.
- `project_report.pdf`: PDF report when a local PDF backend is available.
- `project_report_pdf_unavailable.md`: fallback note when PDF rendering is unavailable.
- `project_report_bundle.zip`: safe bundle containing report assets and key analysis outputs.

## Report Contents

The report summarizes available outputs and marks missing sections as `unavailable` instead of failing:

- cover metadata: project name, HydroLite version, generation time, project path;
- executive summary;
- project overview and enabled modules;
- validation results;
- scenario batch run summary;
- hydrology and routing comparison;
- water balance comparison;
- SWMM results and HydroLite-SWMM coupling status;
- GEE summary outputs when available;
- OpenHydroNet input summary when available;
- observed flow model evaluation when available;
- comparison charts and output file list;
- known limits and disclaimer.

## CLI Usage

Generate all report assets:

```bash
python -m hydrolite report project projects/demo_project
```

Generate individual formats:

```bash
python -m hydrolite report markdown projects/demo_project
python -m hydrolite report docx projects/demo_project
python -m hydrolite report html projects/demo_project
python -m hydrolite report pdf projects/demo_project
python -m hydrolite report bundle projects/demo_project
```

Recommended full project workflow:

```bash
python -m hydrolite project batch projects/demo_project
python -m hydrolite project compare projects/demo_project
python -m hydrolite report project projects/demo_project
python -m hydrolite project export projects/demo_project
```

## Streamlit Usage

Open HydroLite Studio and go to `报告与导出`.

Available actions:

- generate Markdown;
- generate Word;
- generate HTML;
- generate PDF or a PDF unavailable note;
- generate the report bundle;
- one-click generate all report assets;
- download each generated artifact.

On Streamlit Community Cloud, PDF backends may be unavailable. The app will still generate Markdown, Word, HTML, and the report bundle.

## PDF Backend Behavior

HydroLite attempts to render PDF from the HTML report using a supported local backend such as WeasyPrint. If the backend is not installed or fails, HydroLite writes:

```bash
projects/<project>/reports/project_report_pdf_unavailable.md
```

This fallback is intentional. PDF export should not break the rest of the project workflow.

## Bundle Safety Rules

`project_report_bundle.zip` includes only safe report assets and key comparison/validation files. It excludes:

- `external/`;
- `.streamlit/secrets.toml`;
- credentials, token, secret, and service-account file names;
- model weights and checkpoints such as `.pt`, `.pth`, `.ckpt`, `.onnx`;
- Python caches and temporary files.

Generated report files are ignored by git under `projects/*/reports/` so local reports do not accidentally enter the repository.
