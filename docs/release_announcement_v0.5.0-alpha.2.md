# HydroLite Studio v0.5.0-alpha.2

HydroLite Studio v0.5.0-alpha.2 is the first public demo-ready alpha release of HydroLite-Mac, a lightweight local hydrologic and hydraulic modeling workbench for macOS and Streamlit Cloud demos.

This release focuses on a professional project-centered workflow rather than new numerical algorithms.

## Links

- Online demo: https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app
- GitHub repository: https://github.com/Richardomhy/HydroLite-Mac.git
- Current version: `v0.5.0-alpha.2`

The online demo is best for reviewing the interface and example outputs. Run locally for complete GEE authentication, SWMM backend control, and OpenHydroNet external-environment workflows.

## Highlights

- Project-centered Streamlit workbench: HydroLite Studio.
- YAML scenario validation before model runs.
- Single-case and batch scenario execution.
- SCS-CN runoff, simplified unit hydrograph routing, and Muskingum channel routing.
- Water balance checking and scenario comparison reports.
- SWMM coupling through copied `working.inp` files, with graceful backend fallback.
- GEE data center for demo basin summaries and HydroLite input products when user credentials are configured.
- OpenHydroNet-ready input package generation.
- Project export package and release manifest.

## Quick Demo

Online:

```text
https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app
```

Local:

```bash
python -m hydrolite version
python -m hydrolite healthcheck
python -m streamlit run streamlit_app.py --server.headless true
```

Open:

```text
http://localhost:8501
```

Load:

```text
projects/demo_project
```

Recommended demo path:

```text
项目首页 -> 数据与校验 -> 情景运行 -> GEE 数据中心 -> SWMM 联动 -> OpenHydroNet AI 输入 -> 结果对比 -> 报告与导出
```

## Release Assets

- `release/demo_project_package.zip`
- `release/release_manifest.json`
- `release/release_notes_v0.5.0-alpha.md`
- `release/installation_guide.md`
- `release/demo_walkthrough.md`
- `release/known_limitations.md`

## Safety Notes

- `data_raw/` is treated as read-only.
- Google credentials, tokens, API keys, service account files, and `.streamlit/secrets.toml` must not be committed.
- External OpenHydroNet repositories and model weights are not included.
- OpenHydroNet support currently prepares input packages only; it does not run real AI flood prediction.

## Known Limits

HydroLite Studio is not a full MIKE replacement. Demo data are intentionally small, observed streamflow is synthetic/demo only, and engineering decisions still require expert review.
