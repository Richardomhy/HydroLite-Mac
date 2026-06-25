# HydroLite Studio 数据模板与规范校验

HydroLite Studio v0.6.0-dev 提供 `templates/data/` 标准模板，帮助真实工程项目在建模前整理流域、降雨、河道、观测流量、SWMM 入流映射和 GEE 边界数据。

QGIS 用户可以先把子流域、河道和流域边界导出为 GeoJSON，再使用 `python -m hydrolite qgis to-hydrolite ...` 转换为本页模板。详见 `docs/qgis_to_hydrolite_inputs.md`。当前转换是 qgis_process / GeoJSON 文件级自动化，不是完整 QGIS 插件。

## 目的

- 明确每类输入数据需要哪些字段；
- 统一常用单位；
- 降低手写 YAML 和 CSV 的出错概率；
- 在项目向导前完成数据准备；
- 在模型运行前发现缺字段、时间无法解析、数值不合理等问题。

## 模板文件

标准空模板：

- `templates/data/rainfall_template.csv`
- `templates/data/subbasins_template.csv`
- `templates/data/reaches_template.csv`
- `templates/data/observed_streamflow_template.csv`
- `templates/data/swmm_inflow_mapping_template.csv`
- `templates/data/gee_basin_boundary_template.geojson`

示例模板：

- `templates/data/examples/rainfall_example.csv`
- `templates/data/examples/subbasins_example.csv`
- `templates/data/examples/reaches_example.csv`
- `templates/data/examples/observed_streamflow_example.csv`
- `templates/data/examples/swmm_inflow_mapping_example.csv`
- `templates/data/examples/gee_basin_boundary_example.geojson`

## 字段与单位

### rainfall

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `time` | datetime | 降雨时刻，可被 pandas 解析 |
| `rainfall_mm` | mm | 时段降雨量，不应为负 |

### subbasins

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `subbasin_id` | text | 子流域 ID |
| `area_km2` | km2 | 子流域面积，必须 > 0 |
| `cn` | dimensionless | SCS-CN 曲线数，必须满足 0 < CN <= 100 |
| `initial_abstraction_ratio` | dimensionless | 初损比例，常用 0.2 |
| `lag_time_hr` | hour | 滞后时间，必须 >= 0 |
| `outlet_reach_id` | text | 出口河段 ID |

### reaches

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `reach_id` | text | 河段 ID |
| `upstream_reach_id` | text | 上游河段 ID，可空 |
| `downstream_reach_id` | text | 下游河段 ID，可空 |
| `length_km` | km | 河段长度，必须 > 0 |
| `slope` | m/m | 坡度，必须 >= 0 |
| `muskingum_k_hr` | hour | Muskingum K，必须 > 0 |
| `muskingum_x` | dimensionless | Muskingum X，必须 0 <= X <= 0.5 |

### observed_streamflow

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `time` | datetime | 观测时间 |
| `flow_cms` | m3/s | 观测流量 |
| `station_id` | text | 测站 ID |

### swmm_inflow_mapping

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `hydrolite_output_id` | text | HydroLite 输出列或子流域 ID |
| `swmm_node_id` | text | SWMM 节点 ID |
| `scale_factor` | dimensionless | 入流缩放系数，必须 >= 0 |

### gee_basin_boundary

使用 GeoJSON `Polygon` 或 `MultiPolygon`。模板坐标是示意坐标，不代表真实项目。真实工程边界建议先在 GIS 软件中检查投影、拓扑和空间范围。

## 从 Excel 整理为 CSV

1. 按模板字段建立 Excel 表头；
2. 保持字段名英文小写，不要插入合并单元格；
3. 时间列使用 `YYYY-MM-DD HH:MM`；
4. 数值列不要混入单位文本；
5. 另存为 UTF-8 CSV；
6. 使用 HydroLite 的数据模板校验命令检查。

## CLI 用法

```bash
python -m hydrolite templates list
python -m hydrolite templates export rainfall templates_export/
python -m hydrolite templates export-all templates_export/
python -m hydrolite templates validate templates/data/examples/
python -m hydrolite templates summary templates_export/
```

`templates_export/` 是临时导出目录，不应提交到 git。

## Streamlit 用法

打开 HydroLite Studio 后进入 `数据模板` 页面：

- 查看模板列表和字段说明；
- 下载标准模板和示例模板；
- 一键导出全部模板；
- 输入数据目录路径并校验；
- 查看 errors、warnings、字段缺失情况和行数。

## 接入项目向导

真实项目建议流程：

1. 在 `数据模板` 页面下载模板；
2. 用自己的数据填充 CSV/GeoJSON；
3. 校验数据目录；
4. 进入 `项目向导` 页面；
5. 引用整理好的 rainfall、subbasins、reaches、observed streamflow、SWMM INP 和 GEE boundary；
6. 生成项目并运行项目校验。

## 常见错误

- 字段名不一致：例如 `rain` 写成 `rainfall_mm` 才能被识别；
- 时间格式混乱：建议统一为 `YYYY-MM-DD HH:MM`；
- 数值列包含单位文本：例如 `1.2 km2` 应改为 `1.2`；
- CN 超出范围：必须满足 0 < CN <= 100；
- Muskingum X 超出范围：必须满足 0 <= X <= 0.5；
- GeoJSON 类型错误：边界应为 Polygon 或 MultiPolygon。

## 注意事项与免责声明

模板校验只做字段、类型和基础合理性检查，不替代专业水文、水动力或 GIS 审查。真实工程项目仍需由专业人员确认数据来源、测站代表性、空间范围、单位换算和模型适用性。
