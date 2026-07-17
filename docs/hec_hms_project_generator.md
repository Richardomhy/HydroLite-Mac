# HydroLite Studio HEC-HMS 项目生成器 MVP

## 目标

本 MVP 诊断 HEC-HMS 安装、Java 和可执行入口，并将 HydroLite/QGIS/Watershed 数据整理为 HEC-HMS 项目骨架。它不做 GUI 自动化，不执行长时间 HMS 计算，不读取 DSS 结果。

旧目录 `output/hec_hms_project` 继续保留为 `project_generation_mvp / unverified` 诊断成果。新目录 `output/hec_hms_project_verified` 使用官方 4.13 结构校准，已通过真实 `Project.open`，仍必须在 HEC-HMS GUI 或经验证的命令行中人工复核。

## 环境诊断

```bash
python -m hydrolite hms paths
python -m hydrolite hms diagnose
python -m hydrolite hms version
```

诊断检查 macOS、Linux、Windows 常见路径，PATH 中的 `hec-hms` / `hms`，系统 Java 以及 macOS app 内置 Java。对 macOS GUI 启动器，版本优先从 `Info.plist` 读取，避免启动 GUI 或遗留 Java 进程。

当前 Mac 可识别 `/Applications/HEC-HMS-4.13.app`、HEC-HMS 4.13 和 app 内置 OpenJDK 17。内置 Java 的 `-script`、官方参考项目计算和校准项目打开均已验证；校准项目计算仍受降雨门禁阻止，详见 `docs/hec_hms_official_validation.md` 与 `docs/hec_hms_file_format_calibration.md`。

## 支持输入

- `project.yaml`
- `cases/*.yaml` / `*.yml`
- `data/subbasins.csv`
- `data/reaches.csv`
- `data/rainfall.csv`
- 可选 `data/basin_boundary.geojson`
- 可选 QGIS 摘要和已有报告/结果清单

## 生成项目

```bash
python -m hydrolite hms create-project projects/qgis_workflow_project output/hec_hms_project
python -m hydrolite hms validate output/hec_hms_project
python -m hydrolite hms report output/hec_hms_project
```

```text
output/hec_hms_project/
  HydroLite_HMS_Project.hms
  basin/hydrolite_basin.basin
  met/hydrolite_meteorologic.met
  control/hydrolite_control.control
  run/hydrolite_run.run
  data/rainfall_timeseries.csv
  data/subbasin_mapping.csv
  data/reach_mapping.csv
  scripts/run_hms_stub.sh
  scripts/run_hms_stub.bat
  scripts/hydrolite_run_hms.py
  scripts/run_hms.sh
  scripts/run_hms.bat
  reports/hec_hms_project_report.md
  reports/hec_hms_project_manifest.json
  reports/hec_hms_mapping_summary.xlsx
```

## 文件含义

- Basin Model：保留子流域面积、CN、lag，以及河道长度、坡度和 Muskingum K/X 映射。
- Meteorologic Model：生成 `rainfall_timeseries.csv`，并标记 simple precipitation input mapping。
- Control Specifications：从降雨时间推断起止和步长；无法推断时使用 demo 时段并 warning。
- Simulation Run：关联 basin/met/control，但不自动运行。
- Run scripts：保留原安全 stub，并可由 `hms write-run-scripts` 生成 Jython、shell 和 batch 命令；默认仍不执行。

## 人工复核

1. 在 HEC-HMS 4.13 中打开项目或逐个参考生成文件。
2. 复核子流域、河道与出口连通性。
3. 复核面积、时间、流量、降雨和参数单位。
4. 为元素增加 HEC-HMS 所需坐标/几何和时间序列存储。
5. 完成官方最小项目对照和真实运行验证前，不用于工程交付。

## 常见问题与后续路线

- 找不到 HEC-HMS：仍可生成骨架，运行能力标记 unavailable/unverified。
- 系统 Java 不可用：诊断会继续检查 HEC-HMS app 内置 JRE。
- 项目不能运行：检查 HMS 版本、项目语法、时间序列存储、坐标、单位和连通性。
- 下一阶段用官方最小项目对照校验语法，再验证 macOS 命令行入口、最小模拟和 DSS 摘要读取。
# Rainfall-ready project

`create-rainfall-project` creates a separate project under `output/hec_hms_project_rainfall_verified/`, normalizes rainfall, writes and reads back HEC-DSS precipitation, generates the gage/met mapping, and aligns Control Specifications. Earlier generated project folders are not overwritten.
