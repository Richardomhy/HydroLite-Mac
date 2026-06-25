# QGIS / GeoJSON to HydroLite Inputs

## 目标

把 QGIS 或 `qgis_process` 导出的 GeoJSON 图层转换为 HydroLite 标准输入：

- `subbasins.csv`
- `reaches.csv`
- `basin_boundary.geojson`
- `qgis_to_hydrolite_mapping_report.md`
- `qgis_to_hydrolite_summary.xlsx`
- `qgis_to_hydrolite_manifest.json`

当前仍是 `qgis_process` / GeoJSON 文件级自动化，不是完整 QGIS 插件。转换结果可以继续用于一键创建 HydroLite 项目，见 `docs/qgis_project_workflow.md`。

为兼容 HydroLite 数据模板校验，转换目录会写入一个 0 降雨的 `rainfall.csv` 占位文件。真实项目应在项目向导中替换为实际降雨资料。

## QGIS 图层准备要求

推荐在 QGIS 中先准备子流域 polygon、河道 line、流域边界 polygon，并提前计算面积、长度、CN、滞时和 Muskingum 参数字段。HydroLite 当前不做复杂投影面积/长度计算。

## 字段别名规则

子流域目标字段：

- `subbasin_id`
- `area_km2`
- `cn`
- `initial_abstraction_ratio`
- `lag_time_hr`
- `outlet_reach_id`

河道目标字段：

- `reach_id`
- `upstream_reach_id`
- `downstream_reach_id`
- `length_km`
- `slope`
- `muskingum_k_hr`
- `muskingum_x`

常见别名如 `sub_id`、`Shape_Area`、`curve_number`、`rid`、`from_node`、`to_node`、`Shape_Length` 会自动识别。

## 默认值规则

- `initial_abstraction_ratio`: `0.2`
- `cn`: `75`
- `lag_time_hr`: `1.0`
- `muskingum_k_hr`: `2.0`
- `muskingum_x`: `0.2`

ID 缺失时自动生成 `SUB1`、`SUB2` 或 `R1`、`R2`。`area_km2` 和 `length_km` 缺失时留空并记录 warning，不编造真实值。

## 单位转换规则

- `Shape_Area` 且数值明显大于 `10000`：推测为平方米，转换为 km2。
- `Shape_Length` 且数值明显大于 `1000`：推测为米，转换为 km。
- 不做复杂投影计算。

## CLI 用法

```bash
python -m hydrolite qgis infer-mapping data_demo/gis/demo_subbasins.geojson subbasins
python -m hydrolite qgis infer-mapping data_demo/gis/demo_reaches.geojson reaches
python -m hydrolite qgis convert-subbasins data_demo/gis/demo_subbasins.geojson output/qgis_to_hydrolite/subbasins.csv
python -m hydrolite qgis convert-reaches data_demo/gis/demo_reaches.geojson output/qgis_to_hydrolite/reaches.csv
python -m hydrolite qgis export-basin data_demo/gis/demo_basin_boundary.geojson output/qgis_to_hydrolite/basin_boundary.geojson
python -m hydrolite qgis to-hydrolite data_demo/gis/demo_subbasins.geojson data_demo/gis/demo_reaches.geojson data_demo/gis/demo_basin_boundary.geojson output/qgis_to_hydrolite
python -m hydrolite qgis validate-hydrolite output/qgis_to_hydrolite
```

## Streamlit 用法

进入 `QGIS Bridge` 页面，使用“QGIS 图层转 HydroLite 输入”区域，填写三个 GeoJSON 路径和输出目录，然后推断字段映射、转换、校验并下载结果。

## 推荐 QGIS 操作流程

1. 在 QGIS 中整理子流域、河道和边界图层。
2. 用字段计算器补充面积、长度和模型参数字段。
3. 导出 GeoJSON。
4. 用 HydroLite 转换为模板输入。
5. 进入“数据模板”或“项目向导”继续校验和建项目。

## 常见错误

- 字段名不匹配：运行 `infer-mapping` 查看识别结果。
- 面积/长度为空：请在 QGIS 中提前计算字段。
- CSV 校验 warning：查看 mapping report 和 summary workbook。
- QGIS 不可用：GeoJSON 标准库转换仍可执行。

## 当前限制

- 不支持复杂投影面积计算。
- 不自动修复几何。
- 不开发完整 QGIS 插件。
- 不读取 QGIS 工程文件。
