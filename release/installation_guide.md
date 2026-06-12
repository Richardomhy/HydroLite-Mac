# HydroLite Studio Installation Guide

## macOS Local Install

```bash
cd "/Users/minghenyu/Documents/hydrolite 模型"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Conda Environment

```bash
conda create -n hydrolite python=3.11 -y
conda activate hydrolite
python -m pip install -r requirements.txt
```

## SWMM Isolated Environment

Apple Silicon users may need an x86_64/Rosetta conda environment for SWMM backends:

```bash
bash scripts/swmm_env/create_swmm_solver_env.sh
export HYDROLITE_SWMM_PYTHON="$(conda info --base)/envs/hydrolite-swmm-x64/bin/python"
python -m hydrolite run cases/demo_swmm.yaml
```

If SWMM fails, HydroLite writes diagnostics and continues the main watershed workflow.

## GEE Authentication

Set your Google Earth Engine project:

```bash
export GEE_PROJECT="<your-google-cloud-project-id>"
python scripts/gee_auth_local.py
python -m hydrolite gee diagnose
```

Do not commit credentials, tokens, API keys, `.streamlit/secrets.toml`, or files from `~/.config/earthengine`.

## OpenHydroNet External Repository

OpenHydroNet is kept outside git under `external/` or another user-selected path. The current HydroLite release prepares OpenHydroNet-ready input packages only.

```bash
bash scripts/openhydronet_env/clone_openhydronet_repo.sh
python -m hydrolite openhydronet diagnose
python -m hydrolite openhydronet prepare-inputs configs/openhydronet.example.yaml
```

No model training or large inference is run by the HydroLite Studio UI.

## Start Streamlit

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

Open:

```text
http://localhost:8501
```

## GitHub and Streamlit Cloud

GitHub hosts the code. Streamlit Community Cloud runs `streamlit_app.py`.

Recommended settings:

- Repository: your HydroLite GitHub repository
- Branch: `main`
- Main file path: `streamlit_app.py`
- Python version: 3.11

Cloud deployments can show existing outputs and reports even when SWMM, GEE, or OpenHydroNet backends are unavailable.

## Common Issues

- `project.yaml not found`: create or select a valid project folder.
- GEE unavailable: set `GEE_PROJECT`, enable Earth Engine API, and authenticate locally.
- SWMM backend failed: use the isolated solver environment or inspect `swmm_summary.xlsx`.
- OpenHydroNet unavailable: keep using the input package workflow; external repo setup is optional for this alpha.
