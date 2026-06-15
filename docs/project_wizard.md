# HydroLite Studio Project Wizard

HydroLite Studio v0.6.0-dev introduces a project wizard and data import wizard for users who do not want to hand-edit YAML files.

## Goal

The wizard helps users:

- create a project folder;
- choose project name and path;
- enable HydroLite, SWMM, GEE, and OpenHydroNet modules;
- select rainfall, subbasin, reach, observed flow, SWMM INP, and basin boundary files;
- generate `project.yaml`;
- generate case YAML files;
- run project validation;
- review `wizard_summary.md`.

The wizard does not add new model algorithms, does not train OpenHydroNet, and does not run large AI inference.

## Streamlit Page

Open HydroLite Studio and select “项目向导”.

The page includes:

- project name input;
- project path input;
- module checkboxes;
- data path fields;
- template selection;
- preview, create, and validate buttons;
- wizard summary display;
- validation result display.

## CLI Usage

Validate a template:

```bash
python -m hydrolite wizard validate templates/wizard/basic_project.yaml
```

Preview without creating files:

```bash
python -m hydrolite wizard preview templates/wizard/basic_project.yaml
```

Create a project:

```bash
python -m hydrolite wizard create templates/wizard/basic_project.yaml projects/wizard_demo_project
```

Then run:

```bash
python -m hydrolite project validate projects/wizard_demo_project
python -m hydrolite project batch projects/wizard_demo_project
python -m hydrolite project compare projects/wizard_demo_project
```

## Templates

Templates live under `templates/wizard/`:

- `basic_project.yaml`: HydroLite-only demo project.
- `hydrolite_only.yaml`: HydroLite with optional observed flow.
- `hydrolite_gee.yaml`: HydroLite plus GEE module flag and basin boundary.
- `hydrolite_swmm.yaml`: HydroLite plus SWMM coupling.
- `full_demo.yaml`: HydroLite, SWMM, GEE, and OpenHydroNet module flags.

Templates use relative paths and demo data. They do not include secrets or private user paths.

## Data Requirements

Required:

- `rainfall_csv`
- `subbasin_csv`
- `reach_csv`

Optional:

- `observed_streamflow_csv`
- `swmm_inp`
- `basin_boundary`

The wizard can reference input files or copy them into the project data folder. The default templates use reference mode.

## Local and Cloud Differences

Local:

- recommended for full GEE authentication;
- recommended for SWMM isolated solver workflows;
- recommended for OpenHydroNet external repository diagnostics.

Streamlit Cloud:

- suitable for UI demos and sample projects;
- can create demo projects under `projects/`;
- does not require GEE login;
- does not require SWMM backend success;
- does not require OpenHydroNet external repository.

## Common Errors

- Project already exists: choose another folder or delete the generated demo project locally.
- Missing rainfall/subbasin/reach CSV: fix the data path fields.
- SWMM module enabled but no INP: provide `swmm_inp` or disable SWMM.
- Path under `data_raw`: choose a project path outside raw data.

## Next Steps

After project creation:

1. Run project validation.
2. Run one scenario.
3. Run project batch.
4. Generate comparison outputs.
5. Export the project package.
