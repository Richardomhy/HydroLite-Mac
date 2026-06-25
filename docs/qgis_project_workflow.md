# QGIS 转 HydroLite 项目工作流

本阶段打通的是 `qgis_to_hydrolite` 转换结果到 HydroLite 项目向导的最小工作流。它基于 GeoJSON/CSV 文件和 `qgis_process` 命令行能力，不是完整 QGIS 插件，也不依赖 PyQGIS import。

## 输入文件要求

`python -m hydrolite qgis to-hydrolite ...` 输出目录至少需要包含：

- `subbasins.csv`
- `reaches.csv`
- `rainfall.csv`

可选文件：

- `basin_boundary.geojson`
- `qgis_to_hydrolite_manifest.json`
- `qgis_to_hydrolite_mapping_report.md`
- `qgis_to_hydrolite_summary.xlsx`

`subbasins.csv` 可以使用 HydroLite 数据模板字段，例如 `subbasin_id`、`area_km2`、`cn`、`lag_time_hr`。`reaches.csv` 可以使用 `reach_id`、`muskingum_k_hr`、`muskingum_x` 等字段。模型运行时会兼容这些字段和早期 demo 字段。

## rainfall 数据处理

如果创建项目时没有指定 `--rainfall-csv`，系统会引用 `data_demo/rainfall.csv` 作为最小演示降雨输入，并复制到新项目的 `data/rainfall.csv`。

如果用户有自己的降雨文件，可以使用：

```bash
python -m hydrolite qgis create-project output/qgis_to_hydrolite projects/qgis_demo_project --rainfall-csv path/to/rainfall.csv
```

降雨文件仍需满足 HydroLite 校验器要求：包含时间列、子流域编号列和非负降雨字段。

## CLI 用法

先从 QGIS/GeoJSON 图层生成 HydroLite 输入：

```bash
python -m hydrolite qgis to-hydrolite \
  data_demo/gis/demo_subbasins.geojson \
  data_demo/gis/demo_reaches.geojson \
  data_demo/gis/demo_basin_boundary.geojson \
  output/qgis_to_hydrolite
```

校验转换结果：

```bash
python -m hydrolite qgis validate-hydrolite output/qgis_to_hydrolite
```

从转换结果创建 HydroLite 项目：

```bash
python -m hydrolite qgis create-project output/qgis_to_hydrolite projects/qgis_demo_project
```

一键创建并运行完整项目工作流：

```bash
python -m hydrolite qgis project-workflow output/qgis_to_hydrolite projects/qgis_workflow_project
```

该命令默认执行项目创建、项目校验、项目批量运行、结果对比和报告导出。也可以只开启部分步骤：

```bash
python -m hydrolite qgis project-workflow output/qgis_to_hydrolite projects/qgis_workflow_project --run-batch --run-compare
```

## 输出项目结构

新项目会生成：

```text
projects/qgis_demo_project/
  project.yaml
  cases/qgis_demo.yaml
  data/rainfall.csv
  data/subbasins.csv
  data/reaches.csv
  data/basin_boundary.geojson
  output/
  reports/qgis_project_summary.md
  logs/
```

## 校验、运行和报告

创建项目后可继续运行：

```bash
python -m hydrolite project validate projects/qgis_demo_project
python -m hydrolite project batch projects/qgis_demo_project
python -m hydrolite project compare projects/qgis_demo_project
python -m hydrolite report project projects/qgis_demo_project
```

报告输出位于项目 `reports/` 目录，情景结果位于项目 `output/` 目录。

## Streamlit 用法

打开 Streamlit 工作台后进入 `QGIS Bridge` 页面：

1. 先执行 QGIS/GeoJSON 到 HydroLite 输入模板转换；
2. 在“从 QGIS 转换结果创建 HydroLite 项目”区域填写项目目录；
3. 可选填写降雨 CSV；
4. 点击“创建项目”或“运行完整工作流”；
5. 查看 `project.yaml`、`qgis_project_summary.md` 和项目校验/运行结果。

## 当前限制

- 本阶段不是完整 QGIS 插件；
- 不做 PyQGIS import；
- 不自动编辑 QGIS 工程文件；
- 不自动推断复杂拓扑关系；
- 只处理小型 GeoJSON/CSV 演示和标准模板化输入；
- 真实工程仍建议先在 QGIS 中整理字段和坐标，再导出 GeoJSON。

## 常见错误

- `subbasins.csv missing`：先运行 `qgis to-hydrolite` 或检查输出目录；
- `Project already exists`：目标项目目录已存在且非空，请换新目录；
- `rainfall_csv` 字段不符合要求：使用 HydroLite 降雨模板重新整理；
- Muskingum 参数校验失败：检查 `muskingum_k_hr`、`muskingum_x` 和时间步长是否满足稳定性条件。
