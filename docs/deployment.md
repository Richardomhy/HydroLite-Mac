# HydroLite-Mac Deployment

## Why Not GitHub Pages

GitHub Pages serves static HTML, CSS, JavaScript, and assets. It cannot run a Python process, Streamlit server, SWMM backend, or HydroLite model workflow. Use GitHub to host the source code, then use Streamlit Community Cloud to run the app from that repository.

## Recommended Path

Use GitHub + Streamlit Community Cloud:

1. Create a GitHub repository.
2. Push this project to the repository.
3. Create a Streamlit Community Cloud app from the GitHub repository.
4. Set the main file path to `streamlit_app.py`.

## GitHub Repository Setup

```bash
git status
git remote -v
git remote add origin <你的GitHub仓库URL>
git branch -M main
git push -u origin main
```

Replace `<你的GitHub仓库URL>` with your own repository URL.

## Streamlit Community Cloud Settings

- Repository: your HydroLite GitHub repository
- Branch: `main`
- Main file path: `streamlit_app.py`
- Python version: 3.11 is recommended

## Dependency Files

- `requirements.txt` lists Python packages for the app and model workflow.
- `packages.txt` is only needed for Linux apt packages. This project does not currently require one.
- `.streamlit/config.toml` sets headless mode and disables Streamlit usage statistics collection.

## SWMM Cloud Notes

HydroLite's watershed workflow does not require SWMM to succeed. On Streamlit Community Cloud, binary SWMM packages such as `pyswmm` or `swmm-toolkit` may install or run differently from macOS. The app first attempts SWMM backends in the current Python environment. The macOS-only isolated solver path through `HYDROLITE_SWMM_PYTHON` remains available for local runs, but is normally absent in Streamlit Cloud.

If SWMM fails in the cloud, HydroLite still opens the interface, can show existing outputs, validation results, comparison reports, and non-SWMM HydroLite outputs. SWMM failures are recorded in `swmm_summary.xlsx` with `run_status`, `backend_used`, and `error_message`.

## Local Full Model Run

For the full local workflow, including the isolated SWMM solver on macOS:

```bash
python -m hydrolite validate cases/
python -m hydrolite run cases/demo.yaml
python -m hydrolite run cases/demo_swmm.yaml
python -m hydrolite batch cases/
python -m hydrolite compare output/
python -m streamlit run streamlit_app.py --server.headless true
```

If using the isolated SWMM environment:

```bash
bash scripts/swmm_env/create_swmm_solver_env.sh
export HYDROLITE_SWMM_PYTHON="$(conda info --base)/envs/hydrolite-swmm-x64/bin/python"
python -m hydrolite run cases/demo_swmm.yaml
```
