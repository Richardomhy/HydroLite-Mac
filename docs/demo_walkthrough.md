# HydroLite Studio Demo Walkthrough

## 1. Online Demo

Open the public Streamlit Cloud app:

```text
https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app
```

Use the online version to present the UI, demo project, example outputs, reports, and safety boundaries. Cloud execution may not provide the full local GEE/SWMM/OpenHydroNet backend environment.

For a first-time audience, start from the `教程与 Demo` page. It provides Route A for online quick review, Route B for local full workflow, and Route C for engineering deliverables.

## 2. Local Demo

For the complete local workflow, run:

```bash
python -m hydrolite version
python -m hydrolite healthcheck
python -m streamlit run streamlit_app.py --server.headless true
```

Open `http://localhost:8501`.

## 3. Load Demo Project

Use the sidebar project path:

```text
projects/demo_project
```

Open “项目首页” and confirm the project name, modules, cases, and `project_summary.md`.

You can also open “教程与 Demo” and use the built-in checklist while presenting each step.

## 4. Validate Project

Open “数据与校验” and click “校验当前项目”. Review failed and warning counts.

## 5. Run demo_gee

Open “情景运行”, select `demo_gee.yaml`, and click “运行选中情景”. Review `result_flow.csv`, `water_balance.xlsx`, the hydrograph, and model performance outputs.

## 6. Run Batch Scenarios

Still in “情景运行”, click “批量运行项目情景”. Review `batch_summary.xlsx`.

## 7. View GEE Data Center

Open “GEE 数据中心”. Review GEE status, supported datasets, basin summary, CHIRPS rainfall, temperature, parameter suggestions, and report outputs.

## 8. View OpenHydroNet AI Input

Open “OpenHydroNet AI 输入”. Confirm the page states this is an OpenHydroNet-ready input package, not a real AI prediction. Review meteorological forcing, observed streamflow, HydroLite streamflow, and input quality report.

## 9. View SWMM Coupling

Open “SWMM 联动”. Select the SWMM case and review `swmm_summary.xlsx`, `swmm_kpis.xlsx`, `coupling_summary.xlsx`, node depths, link flows, and system time series.

## 10. Compare Results

Open “结果对比” and click “生成项目对比”. Review overview, hydrology metrics, water balance, SWMM metrics, coupling metrics, performance metrics, and comparison charts.

## 11. Export Project Package

Open “报告与导出” and click “导出项目包”. Download:

```text
projects/demo_project/reports/demo_project_package.zip
```
