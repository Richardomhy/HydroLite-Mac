# HydroLite Studio Demo Walkthrough

## 1. Open HydroLite Studio

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

Open `http://localhost:8501`.

## 2. Load Demo Project

Use the sidebar project path:

```text
projects/demo_project
```

Open “项目首页” and confirm the project name, modules, cases, and `project_summary.md`.

## 3. Validate Project

Open “数据与校验” and click “校验当前项目”. Review failed and warning counts.

## 4. Run demo_gee

Open “情景运行”, select `demo_gee.yaml`, and click “运行选中情景”. Review `result_flow.csv`, `water_balance.xlsx`, the hydrograph, and model performance outputs.

## 5. Run Batch Scenarios

Still in “情景运行”, click “批量运行项目情景”. Review `batch_summary.xlsx`.

## 6. View GEE Data Center

Open “GEE 数据中心”. Review GEE status, supported datasets, basin summary, CHIRPS rainfall, temperature, parameter suggestions, and report outputs.

## 7. View OpenHydroNet AI Input

Open “OpenHydroNet AI 输入”. Confirm the page states this is an OpenHydroNet-ready input package, not a real AI prediction. Review meteorological forcing, observed streamflow, HydroLite streamflow, and input quality report.

## 8. View SWMM Coupling

Open “SWMM 联动”. Select the SWMM case and review `swmm_summary.xlsx`, `swmm_kpis.xlsx`, `coupling_summary.xlsx`, node depths, link flows, and system time series.

## 9. Compare Results

Open “结果对比” and click “生成项目对比”. Review overview, hydrology metrics, water balance, SWMM metrics, coupling metrics, performance metrics, and comparison charts.

## 10. Export Project Package

Open “报告与导出” and click “导出项目包”. Download:

```text
projects/demo_project/reports/demo_project_package.zip
```
