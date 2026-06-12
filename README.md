# HydroLite-Mac

HydroLite-Mac is a local lightweight hydrologic and hydraulic modeling MVP for macOS. It supports YAML-based cases, CSV inputs, SCS-CN runoff generation, simplified unit hydrograph routing, Muskingum channel routing, water balance checks, batch runs, and a local Streamlit interface.

## Install

```bash
cd "/Users/minghenyu/Documents/hydrolite 模型"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Quick Start Local

```bash
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
