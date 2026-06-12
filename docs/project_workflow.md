# HydroLite Project Workflow

HydroLite projects provide a professional workspace around the existing lightweight modeling workflow. They do not add new hydrologic algorithms, SWMM algorithms, AI training, or external inference. The project layer only organizes configuration, execution, comparison, reporting, and packaging.

## Project Layout

```text
projects/demo_project/
  project.yaml
  project_summary.md
  cases/
  configs/
  data/
  output/
  reports/
  logs/
```

`project.yaml` records the project name, project ID, paths, enabled modules, default cases, and notes. Demo project cases reference the repository demo data through relative paths, so `data_raw/` remains read-only and is not copied into the project package.

## Commands

Create a demo project:

```bash
python -m hydrolite project create projects/demo_project
```

Inspect metadata:

```bash
python -m hydrolite project info projects/demo_project
```

Validate all project cases:

```bash
python -m hydrolite project validate projects/demo_project
```

Run one project case:

```bash
python -m hydrolite project run projects/demo_project demo_gee.yaml
```

Run all project cases:

```bash
python -m hydrolite project batch projects/demo_project
```

Compare project outputs:

```bash
python -m hydrolite project compare projects/demo_project
```

Export a portable package:

```bash
python -m hydrolite project export projects/demo_project
```

## Outputs

Project case outputs are written to `projects/<project>/output/<case_name>/`. Project validation writes:

- `projects/<project>/reports/project_validation.xlsx`
- `projects/<project>/reports/project_validation_report.md`

Project comparison writes:

- `projects/<project>/output/comparison/scenario_comparison.xlsx`
- `projects/<project>/output/comparison/scenario_comparison.csv`
- `projects/<project>/output/comparison/hydrolite_report.md`
- comparison figures under `projects/<project>/output/comparison/`

Project export writes:

- `projects/<project>/reports/<project_id>_package.zip`

The package includes `project.yaml`, project cases, project configs, reports, project summary, and comparison outputs. It excludes `.streamlit/secrets.toml`, `external/`, virtual environments, generated zip files, and model weight files such as `.pt`, `.pth`, `.ckpt`, and `.onnx`.

## Streamlit

The Streamlit app includes a project management area. It can display project metadata, validate a project, run a selected project case, run a project batch, generate project comparison outputs, and export the project package.

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

## Data Safety

Project commands must not modify or delete existing files under `data_raw/`. SWMM project cases copy `data_raw/swmm/demo.inp` to a project-local `working.inp` before modifying any coupling boundary conditions.

## Compatibility

The original commands remain unchanged:

```bash
python -m hydrolite validate cases/
python -m hydrolite run cases/demo.yaml
python -m hydrolite batch cases/
python -m hydrolite compare output/
```
