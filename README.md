# HydroLite-Mac

HydroLite-Mac is a local lightweight hydrologic and hydraulic modeling MVP for macOS. It supports YAML-based cases, CSV inputs, SCS-CN runoff generation, simplified unit hydrograph routing, Muskingum channel routing, water balance checks, batch runs, and a local Streamlit interface.

## Install

```bash
cd "/Users/minghenyu/Documents/hydrolite 模型"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
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
python -m streamlit run hydrolite/ui/app.py --server.headless true
```

Then open:

```text
http://localhost:8501
```

## Outputs

Single-case outputs are written to `output/<case_name>/`:

- `result_flow.csv`: routed inflow and outlet hydrograph time series.
- `summary.xlsx`: basic run metrics and peak flow summary.
- `hydrograph.png`: inflow and outflow hydrograph plot.
- `water_balance.xlsx`: `subbasin_balance` and `outlet_balance` sheets.
- `run.log`: run log with input paths, parameters, Muskingum checks, outputs, and runtime.

Batch runs also write:

- `output/batch_summary.xlsx`: per-case status, runtime, output folder, peak flow, volume, water balance error, and error message.

## Raw Data Safety

`data_raw/` is reserved for original raw data. HydroLite should not modify or delete files under `data_raw/`. Demo inputs live in `data_demo/`, and generated outputs are written under `output/`.

## SWMM on macOS Backend Notes

HydroLite's main watershed workflow does not depend on SWMM succeeding. If the local SWMM Python backends fail because of macOS binary compatibility, HydroLite still writes the normal `result_flow.csv`, `summary.xlsx`, `hydrograph.png`, and `water_balance.xlsx` outputs and records SWMM diagnostics in `swmm_summary.xlsx`.

For SWMM on macOS, especially Apple Silicon, use the isolated solver environment:

```bash
bash scripts/swmm_env/create_swmm_solver_env.sh
export HYDROLITE_SWMM_PYTHON="$(conda info --base)/envs/hydrolite-swmm-x64/bin/python"
python -m hydrolite run cases/demo_swmm.yaml
```

On Apple Silicon, the script first tries an x86_64 conda environment using `CONDA_SUBDIR=osx-64`, which requires Rosetta 2. Diagnostics are written to `output/swmm_solver_env_diagnosis.txt`.
