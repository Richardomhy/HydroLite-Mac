# HydroLite Studio v0.7.0-dev

[![Release](https://img.shields.io/badge/release-v0.6.0--beta.1-blue)](https://github.com/Richardomhy/HydroLite-Mac/releases/tag/v0.6.0-beta.1)
[![Streamlit](https://img.shields.io/badge/Streamlit-Cloud%20demo-ff4b4b)](https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app)

- GitHub repository: https://github.com/Richardomhy/HydroLite-Mac.git
- Streamlit Cloud online demo: https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app
- Current development version: `v0.7.0-dev`
- Current stable beta: `v0.6.0-beta.1`

The online version is best for demos, tutorials, data template downloads, and viewing example outputs; the local version is recommended for complete GEE, SWMM, OpenHydroNet-ready input, and project delivery workflows.

HydroLite-Mac is a local lightweight hydrologic and hydraulic modeling MVP for macOS. HydroLite Studio v0.7.0-dev starts the next development phase: a full modeling workflow engine for data templates, QGIS/GEE preprocessing, HydroLite simulation, future HEC-HMS bridges, SWMM coupling, forecast planning, comparison, reports, and user manuals. The current stable beta remains v0.6.0-beta.1.

Latest beta release: **v0.6.0-beta.1**.

Previous beta tag: **v0.6.0-beta**.

Previous stable alpha tag: **v0.5.0-alpha.2**.

Next development plan: **v0.7.x full workflow architecture**. This is planning only plus orchestration scaffolding, not a claim that every stage is implemented. Start with `docs/full_modeling_workflow.md` and `docs/roadmap_v0.7.0.md`.

Quick demo entry points:

- 在线体验：https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app
- 中文快速开始：`docs/quickstart_zh.md`
- 中文演示脚本：`docs/demo_script_zh.md`
- GitHub Release 发布说明：`docs/release_announcement_v0.5.0-alpha.2.md`
- Beta 发布说明：`docs/release_announcement_v0.6.0-beta.1.md`
- FAQ：`docs/faq_zh.md`
- 数据模板：`docs/data_templates.md`
- 项目向导：`docs/project_wizard.md`
- 全流程工作流：`docs/full_modeling_workflow.md`
- v0.7.0 路线图：`docs/roadmap_v0.7.0.md`

## Beta Feature Overview

- Project workflow with project-local cases, configs, outputs, reports, and package export.
- Streamlit professional workbench with pages for tutorial, data templates, validation, scenarios, GEE, SWMM, OpenHydroNet-ready inputs, comparison, and reports.
- Project wizard for creating projects without hand-editing YAML.
- Real-project CSV/GeoJSON data templates and data specification validation.
- Guided tutorial and demo mode for first-time users.
- One-click Markdown, Word, HTML, PDF fallback, and report bundle export.
- GEE data center outputs and HydroLite input product handoff.
- SWMM coupling and result extraction with graceful backend fallback.
- OpenHydroNet-ready input package generation without training or large inference.
- Observed streamflow import and model evaluation metrics.

## v0.7.0 Planning

v0.6.0-beta.1 is the current stable beta. v0.7.0-dev is the active development branch for full workflow orchestration. HEC-HMS, watershed delineation, flood forecasting, drought forecasting, calibration, and user-manual export are staged as planned or partial work until implemented and tested.

The first v0.7.0 step is QGIS Bridge feasibility diagnosis only. It checks QGIS/QGIS-LTR/qgis_process/PyQGIS availability and does not implement a full QGIS plugin.

The current QGIS Bridge MVP uses `qgis_process` for command-line checks and small GeoJSON/CSV demo exports. It is still not a full QGIS plugin. It can also convert QGIS-exported GeoJSON layers into HydroLite input templates and create a runnable HydroLite project from those converted outputs; see `docs/qgis_to_hydrolite_inputs.md` and `docs/qgis_project_workflow.md`.

The watershed delineation MVP probes QGIS/GRASS/SAGA-style processing availability, creates a tiny synthetic DEM, runs QGIS sink filling and D8 flow direction when available, and uses HydroLite's deterministic topology engine for flow accumulation and stream extraction. Outlet-based basin geometry remains an explicitly marked fallback and still requires GIS review. See `docs/watershed_delineation_mvp.md`.

The HEC-HMS bridge diagnoses HEC-HMS and Java, validates the official `Project.open / computeRun` script flow, and calibrates a HydroLite-generated project against HEC-HMS 4.13 component structure. The calibrated project passes `Project.open` and exposes a Run; compute remains gated until a supported rainfall source is available. It does not automate the GUI or deeply read DSS results. See `docs/hec_hms_official_validation.md`, `docs/hec_hms_file_format_calibration.md`, `docs/hec_hms_project_generator.md`, and `docs/hec_hms_run_mvp.md`.

```bash
python -m hydrolite watershed backends
python -m hydrolite watershed mvp
python -m hydrolite watershed validate output/watershed
python -m hydrolite hms diagnose
python -m hydrolite hms create-project projects/qgis_workflow_project output/hec_hms_project
python -m hydrolite hms run-probe
python -m hydrolite hms run output/hec_hms_project --dry-run
```

The v0.7.0 workflow engine can list stages, create dry-run plans, and write workflow status/report files:

```bash
python -m hydrolite workflow list
python -m hydrolite workflow plan templates/workflows/full_modeling_workflow.yaml output/workflow_plan
python -m hydrolite workflow run-full projects/demo_project --dry-run
```

`dry-run` is the default. Planned stages are not executed and are not advertised as available model capabilities.

Planning documents:

- `docs/roadmap_v0.7.0.md`
- `docs/full_modeling_workflow.md`
- `docs/hec_hms_integration_plan.md`
- `docs/hec_hms_project_generator.md`
- `docs/hec_hms_run_mvp.md`
- `docs/watershed_delineation_plan.md`
- `docs/watershed_delineation_mvp.md`
- `docs/flood_forecast_plan.md`
- `docs/drought_forecast_plan.md`
- `docs/user_manual_plan.md`
- `docs/milestones_v0.7.0.md`
- `docs/issue_backlog_v0.7.0.md`
- `docs/qgis_bridge_roadmap.md`
- `docs/qgis_bridge_diagnosis.md`
- `docs/qgis_process_bridge.md`
- `docs/qgis_to_hydrolite_inputs.md`
- `docs/qgis_project_workflow.md`
- `docs/calibration_roadmap.md`
- `docs/desktop_app_roadmap.md`

## Recommended Demo Flow

```text
教程与 Demo -> 数据模板 -> 项目向导 -> 数据与校验 -> 情景运行 -> GEE 数据中心 -> SWMM 联动 -> OpenHydroNet AI 输入 -> 结果对比 -> 报告与导出
```

## Real Project Workflow

1. 下载 `templates/data/` 数据模板；
2. 整理 rainfall、subbasins、reaches、observed streamflow、SWMM mapping 和 GEE boundary；
3. 使用项目向导创建项目；
4. 校验数据与项目；
5. 运行单情景或批量情景；
6. 查看结果对比；
7. 导出 Markdown / Word / HTML / PDF fallback 报告和项目包。

## Beta Feedback

Beta users can use the Streamlit `Beta 反馈` page, GitHub Issue templates, and `docs/beta_feedback_workflow.md` to report usability issues, missing checks, documentation gaps, UI problems, or local environment failures.

## Quick Start

```bash
python -m hydrolite version
python -m hydrolite healthcheck
python -m hydrolite roadmap
python -m streamlit run streamlit_app.py --server.headless true
```

Open `http://localhost:8501`, then load `projects/demo_project`.

普通用户推荐流程：

```text
项目向导 -> 数据与校验 -> 情景运行 -> 结果对比 -> 报告与导出
```

CLI project wizard:

```bash
python -m hydrolite wizard preview templates/wizard/basic_project.yaml
python -m hydrolite wizard create templates/wizard/basic_project.yaml projects/wizard_demo_project
python -m hydrolite project validate projects/wizard_demo_project
```

## Install

```bash
cd "/Users/minghenyu/Documents/hydrolite 模型"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Quick Start Local

```bash
python -m hydrolite version
python -m hydrolite healthcheck
python -m hydrolite validate cases/
python -m hydrolite run cases/demo.yaml
python -m hydrolite run cases/demo_swmm.yaml
python -m hydrolite batch cases/
python -m hydrolite compare output/
python -m streamlit run streamlit_app.py --server.headless true
```

## Run One Case

```bash
python -m hydrolite run cases/demo.yaml
```

## Run All Cases

```bash
python -m hydrolite batch cases/
```

## Project Workflow

HydroLite can also organize a modeling job as a project folder. A project wraps cases, configs, project-local outputs, reports, and export packaging while preserving the legacy `cases/`, `configs/`, `data_demo/`, and `output/` workflows.

```bash
python -m hydrolite project create projects/demo_project
python -m hydrolite project info projects/demo_project
python -m hydrolite project validate projects/demo_project
python -m hydrolite project run projects/demo_project demo_gee.yaml
python -m hydrolite project batch projects/demo_project
python -m hydrolite project compare projects/demo_project
python -m hydrolite project export projects/demo_project
```

Project exports are written to `projects/<project_id>/reports/<project_id>_package.zip`. The export excludes secrets, external repositories, virtual environments, raw external model weights, and generated zip files. See `docs/project_workflow.md`.

## Start Streamlit UI

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

Then open:

```text
http://localhost:8501
```

If the browser does not open, try:

```text
http://127.0.0.1:8501
```

You can also run:

```bash
python scripts/diagnose_streamlit_local.py
```

The diagnosis is written to `output/streamlit_local_diagnosis.txt`.

## HydroLite Studio UI

The Streamlit interface is organized as **HydroLite Studio**, a project-centered workbench. It includes:

- 项目首页
- 数据与校验
- 情景运行
- GEE 数据中心
- SWMM 联动
- OpenHydroNet AI 输入
- 结果对比
- 报告与导出
- 系统诊断

Recommended UI workflow:

```text
项目首页 -> 数据与校验 -> 情景运行 -> 结果对比 -> 报告与导出
```

Use the GEE, SWMM, and OpenHydroNet pages only when those modules are needed. See `docs/ui_workbench.md` for page-by-page guidance and local/cloud differences.

## Demo Workflow

```bash
python -m hydrolite project validate projects/demo_project
python -m hydrolite project run projects/demo_project demo_gee.yaml
python -m hydrolite project batch projects/demo_project
python -m hydrolite project compare projects/demo_project
python -m hydrolite project export projects/demo_project
```

For a guided public demonstration, follow `docs/demo_script_zh.md`.

## Capability Matrix

| Area | v0.5.0-alpha status |
| --- | --- |
| SCS-CN runoff | Available |
| Simplified unit hydrograph | Available |
| Muskingum routing and stability checks | Available |
| Water balance checks | Available |
| Project workflow | Available |
| Streamlit Studio workbench | Available |
| GEE data center | Available when user GEE credentials/project are configured |
| SWMM coupling | Available with graceful backend fallback |
| OpenHydroNet | Input package only; no real AI prediction |
| MIKE replacement | Not a full replacement |

## Documentation Index

- `docs/ui_workbench.md`: HydroLite Studio workbench guide.
- `docs/project_wizard.md`: project wizard and data import wizard guide.
- `docs/tutorial_demo.md`: guided in-app tutorial and demo mode.
- `docs/data_templates.md`: real project CSV/GeoJSON templates and validation guide.
- `docs/report_export.md`: one-click Markdown, Word, HTML, PDF, and report bundle export.
- `docs/project_workflow.md`: project folder workflow.
- `docs/release_notes_v0.5.0-alpha.md`: release notes.
- `docs/release_announcement_v0.5.0-alpha.2.md`: GitHub Release announcement.
- `docs/quickstart_zh.md`: Chinese quick start.
- `docs/demo_script_zh.md`: Chinese demo presenter script.
- `docs/faq_zh.md`: Chinese FAQ.
- `docs/release_notes_v0.6.0-beta.md`: beta release notes.
- `docs/release_announcement_v0.6.0-beta.md`: beta user-facing announcement.
- `docs/release_notes_v0.6.0-beta.1.md`: beta.1 patch release notes.
- `docs/release_announcement_v0.6.0-beta.1.md`: beta.1 user-facing announcement.
- `docs/beta_test_plan.md`: beta test plan.
- `docs/beta_user_feedback.md`: beta feedback template.
- `docs/post_release_validation.md`: post-release validation checklist.
- `docs/cloud_smoke_test.md`: Streamlit Cloud smoke test.
- `docs/local_smoke_test.md`: local smoke test.
- `docs/beta_feedback_workflow.md`: beta feedback triage workflow.
- `docs/v0.6.0_beta_checklist.md`: beta release checklist.
- `docs/v0.6.0_beta_1_checklist.md`: beta.1 patch release checklist.
- `docs/roadmap_v0.7.0.md`: v0.7.0 planning roadmap.
- `docs/milestones_v0.7.0.md`: v0.7.0 milestone plan.
- `docs/issue_backlog_v0.7.0.md`: GitHub Issue backlog draft.
- `docs/qgis_bridge_roadmap.md`: QGIS Bridge plan.
- `docs/qgis_bridge_diagnosis.md`: QGIS Bridge feasibility diagnosis guide.
- `docs/qgis_process_bridge.md`: qgis_process Bridge MVP guide.
- `docs/qgis_to_hydrolite_inputs.md`: QGIS/GeoJSON layer to HydroLite input conversion guide.
- `docs/calibration_roadmap.md`: lightweight calibration plan.
- `docs/desktop_app_roadmap.md`: desktop app evaluation plan.
- `docs/installation_guide.md`: install and deployment guide.
- `docs/demo_walkthrough.md`: end-to-end demo.
- `docs/known_limitations.md`: limitations and non-use cases.
- `docs/release_checklist.md`: release verification checklist.

Known limitations are summarized in `docs/known_limitations.md`.

## Deploy to Streamlit Community Cloud

GitHub Pages cannot run Streamlit or Python services. Use GitHub for source hosting and Streamlit Community Cloud for the running app.

Streamlit Community Cloud settings:

- Repository: your HydroLite GitHub repository
- Branch: `main`
- Main file path: `streamlit_app.py`
- Python version: 3.11 recommended

See `docs/deployment.md` and `docs/github_push_commands.md` for the push and deployment templates.

## Outputs

Single-case outputs are written to `output/<case_name>/`:

- `result_flow.csv`: routed inflow and outlet hydrograph time series.
- `summary.xlsx`: basic run metrics and peak flow summary.
- `hydrograph.png`: inflow and outflow hydrograph plot.
- `water_balance.xlsx`: `subbasin_balance` and `outlet_balance` sheets.
- `observed_vs_simulated.csv`: aligned observed and simulated streamflow when `observed.enabled` is true.
- `model_performance.xlsx`: NSE, RMSE, MAE, PBIAS, R2, and KGE metrics plus aligned timeseries.
- `observed_vs_simulated.png`: observed/simulated hydrograph comparison.
- `run.log`: run log with input paths, parameters, Muskingum checks, outputs, and runtime.

Batch runs also write:

- `output/batch_summary.xlsx`: per-case status, runtime, output folder, peak flow, volume, water balance error, and error message.

## Project Report Export

Project reports can be generated from existing validation, batch, comparison, SWMM, GEE, OpenHydroNet, and observed-flow outputs:

```bash
python -m hydrolite report project projects/demo_project
```

This writes `project_report.md`, `project_report.docx`, `project_report.html`, `project_report.pdf` when a PDF backend is available, or `project_report_pdf_unavailable.md` as a fallback. A safe `project_report_bundle.zip` is also generated for sharing. See `docs/report_export.md`.

## Guided Demo

First-time users should start from the Streamlit `教程与 Demo` page. It provides a step-by-step route through `projects/demo_project`, validation, scenario runs, GEE, SWMM, OpenHydroNet input packaging, comparison, report export, and online/local deployment differences.

CLI helpers are also available:

```bash
python -m hydrolite tutorial list
python -m hydrolite tutorial checklist projects/demo_project
python -m hydrolite tutorial summary projects/demo_project
```

See `docs/tutorial_demo.md`.

## Real Project Data Templates

Before creating a real project, download the standard templates under `templates/data/`, organize rainfall, subbasins, reaches, observed streamflow, SWMM inflow mapping, and GEE basin boundary files, then use the project wizard.

```bash
python -m hydrolite templates list
python -m hydrolite templates export-all templates_export/
python -m hydrolite templates validate templates/data/examples/
```

See `docs/data_templates.md`.

## Raw Data Safety

`data_raw/` is reserved for original raw data. HydroLite should not modify or delete files under `data_raw/`. Demo inputs live in `data_demo/`, and generated outputs are written under `output/`.

## Observed Streamflow Evaluation

`cases/demo_gee.yaml` includes an optional observed streamflow block that points to `data_demo/observed/demo_observed_streamflow.csv`. This file is synthetic/demo only and is not real gauge data. It is used to exercise model evaluation and OpenHydroNet input packaging.

When observed data is enabled, HydroLite aligns observed and simulated streamflow and writes model performance outputs under `output/<case_name>/`.

## SWMM on macOS Backend Notes

HydroLite's main watershed workflow does not depend on SWMM succeeding. If the local SWMM Python backends fail because of macOS binary compatibility, HydroLite still writes the normal `result_flow.csv`, `summary.xlsx`, `hydrograph.png`, and `water_balance.xlsx` outputs and records SWMM diagnostics in `swmm_summary.xlsx`.

On Streamlit Community Cloud, HydroLite first tries SWMM packages in the current Python environment. If cloud SWMM binaries fail, the interface remains usable for existing outputs, validation, batch summaries, scenario comparison, and non-SWMM runs. The macOS isolated solver remains available locally through `HYDROLITE_SWMM_PYTHON`.

For SWMM on macOS, especially Apple Silicon, use the isolated solver environment:

```bash
bash scripts/swmm_env/create_swmm_solver_env.sh
export HYDROLITE_SWMM_PYTHON="$(conda info --base)/envs/hydrolite-swmm-x64/bin/python"
python -m hydrolite run cases/demo_swmm.yaml
```

On Apple Silicon, the script first tries an x86_64 conda environment using `CONDA_SUBDIR=osx-64`, which requires Rosetta 2. Diagnostics are written to `output/swmm_solver_env_diagnosis.txt`.

## HydroLite to SWMM Coupling

SWMM cases can inject a HydroLite flow hydrograph into the copied `working.inp` file through `swmm.coupling`. The demo uses `source_time_column: time` and `source_flow_column: outflow_cms`, matching HydroLite's current `result_flow.csv` outlet flow field.

The original `data_raw/swmm/demo.inp` is not edited. Coupling writes `[TIMESERIES]` and `[INFLOWS]` only into `output/<case_name>/swmm/working.inp`, then writes `coupling_summary.xlsx`.
