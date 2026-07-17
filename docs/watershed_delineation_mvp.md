# HydroLite Studio 流域划分 MVP

## 目标

流域划分 MVP 用于验证 macOS 上的 DEM 诊断、`qgis_process` 水文算法探测和 HydroLite 数据交付链。它不是完整 QGIS 插件，不依赖 PyQGIS import，也不替代专业 GIS 人工复核。

## DEM 输入

- MVP 默认使用 `data_demo/gis/demo_dem.asc`。
- demo DEM 是 12 x 12 的合成 ASCII Grid，包含规则坡面、沟槽和小洼地。
- 坐标是无敏感地理含义的局部示例坐标，不可用作真实工程定位。
- 真实 DEM 应先检查投影、分辨率、NoData、范围和高程单位。

## 后端探测

`python -m hydrolite watershed backends` 会扫描 `qgis_process list`，检查 GRASS、SAGA、watershed、fill sinks、flow accumulation、TauDEM 和 Whitebox 等关键字。状态含义：

- `available`：发现完整候选链，仍需人工复核。
- `partial`：只有部分 QGIS 算法，其余阶段使用明确标注的 fallback。
- `fallback`：未发现稳定链，仅生成小型诊断示例。
- `unavailable`：后端和 fallback 都不可用。当前 MVP 自带轻量 fallback，通常不会进入此状态。

当 `native:fillsinkswangliu` 可用时，填洼优先通过 `qgis_process` 运行。汇流累积、河网和分区若缺少稳定后端，使用小型 Python D8/fallback 示例，文件属性中会写入 `is_fallback: true`。

## 使用

```bash
python -m hydrolite watershed backends
python -m hydrolite watershed create-demo-dem output/watershed/demo_dem.asc
python -m hydrolite watershed inspect output/watershed/demo_dem.asc
python -m hydrolite watershed mvp
python -m hydrolite watershed validate output/watershed
python -m hydrolite watershed report output/watershed
```

Streamlit 中从主导航进入“流域划分”页面。

## 输出

`output/watershed/` 包含：

- `watershed_diagnosis.json`
- `watershed_report.md`
- `watershed_backend_summary.xlsx`
- `demo_dem.asc`
- `filled_dem.asc`
- `flow_accumulation.asc`
- `basin_boundary.geojson`
- `stream_network.geojson`
- `subbasins.geojson`
- `hydrolite_subbasins.csv`
- `hydrolite_reaches.csv`

两个 CSV 使用 HydroLite 现有数据模板字段，`watershed validate` 会调用数据模板校验器。

## 接入 QGIS -> HydroLite

1. 在“流域划分”页或 CLI 生成产物。
2. 在 QGIS 中打开 GeoJSON，人工复核河网、边界、出口点和投影。
3. 将复核后图层导出为 QGIS Bridge 支持的 GeoJSON。
4. 运行 `python -m hydrolite qgis to-hydrolite ...`。
5. 运行 `python -m hydrolite qgis project-workflow ...`创建项目。

## 当前限制

- 不执行大流域或长时间栅格任务。
- 不做真实出口点吸附和专业子流域划分。
- fallback 边界基于 demo DEM 范围，不是真实地形分水岭。
- 河网阈值是小样例规则，不是工程标定值。
- GRASS/SAGA/Whitebox/TauDEM 的安装与专业算法适配属于后续路线。

## 人工复核

真实项目必须在 GIS 中复核 DEM 投影和分辨率、水系烧入/平坦区处理、汇流阈值、出口点位置、河网连通性、分水岭和流域面积。

