# GEE 数据中心插件骨架

## 目标

GEE 数据中心用于未来从 Google Earth Engine 获取遥感、DEM、土地利用、降雨、水体和植被指数等数据，为 HydroLite 水文建模和 OpenHydroNet AI 洪水预测提供输入支撑。

当前阶段支持安全的真实 Earth Engine 初始化：如果本机或云端已经配置好凭证，HydroLite 会调用 `ee.Initialize(project=...)`；如果没有凭证，只返回 `unavailable` 并显示操作提示，不会强制弹出浏览器认证。

## 初始支持数据类型

- DEM：地形高程和地形衍生参数。
- landcover：土地利用/覆盖分类。
- precipitation：卫星或融合降雨。
- ndvi：植被指数。
- water_index：水体指数占位。
- surface_water：长期地表水产品。

## 本地认证方式

支持以下来源：

- 本地 Earth Engine credentials。
- `GOOGLE_APPLICATION_CREDENTIALS` 指向 service account JSON。
- `GEE_PROJECT` 指定 Google Cloud 项目。
- `GOOGLE_CLOUD_PROJECT` 指定 Google Cloud 项目。
- Streamlit Cloud secrets 中的 `[gee] project = "..."`。
- 配置文件中的 `project` 字段。
- 本地 `configs/gee.local.yaml`，该文件已加入 `.gitignore`。

本地认证推荐：

```bash
python scripts/gee_auth_local.py
python -c "import ee; ee.Authenticate()"
export GEE_PROJECT="你的project"
python scripts/diagnose_gee.py
```

Google Cloud Project 需要启用 Earth Engine API，并且账号需要有 Earth Engine 权限。

## Streamlit Cloud Secrets 注意事项

Streamlit Cloud 可通过 secrets 管理敏感信息，但不要提交 `.streamlit/secrets.toml`。仓库中只允许提交 `.streamlit/config.toml` 这类非敏感配置。

示例：

```toml
[gee]
project = "你的project"
```

## Secrets 安全规则

- 不提交 Google service account JSON。
- 不提交 API key、token、client secret。
- 不把 `.streamlit/secrets.toml` 加入 git。
- 不把真实账号路径写死到代码中。

## 后续开发路线

最小示例流域：

```text
data_demo/gee/demo_basin.geojson
```

示例命令：

```bash
python -m hydrolite gee diagnose
python -m hydrolite gee plan configs/gee.example.yaml
python -m hydrolite gee summarize configs/gee.example.yaml
python -m hydrolite gee hydrolite-inputs configs/gee.example.yaml
```

输出：

```text
output/gee/gee_data_plan.xlsx
output/gee/gee_summary.xlsx
output/gee/gee_summary.csv
output/gee/gee_report.md
```

## 从 GEE 生成 HydroLite 输入

运行：

```bash
export GEE_PROJECT="你的project"
python -m hydrolite gee hydrolite-inputs configs/gee.example.yaml
```

输出目录：

```text
output/gee/hydrolite_inputs/
```

主要文件：

```text
gee_basin_summary.xlsx
gee_basin_summary.csv
gee_chirps_rainfall.csv
gee_parameter_suggestions.xlsx
gee_parameter_suggestions.yaml
gee_to_hydrolite_report.md
```

`gee_chirps_rainfall.csv` 兼容 HydroLite 降雨输入，包含：

- `datetime`
- `time`
- `subbasin_id`
- `rain_mm`

其中 `subbasin_id` 当前使用 `GEE_BASIN_1`。

## 参数建议说明

`gee_parameter_suggestions` 基于透明启发式生成：

- CN 根据 JRC surface water occurrence 和 CHIRPS 降雨统计给出 70-85 的初始建议。
- lag_hours 根据 bbox 面积和 DEM 高差粗略估计。
- Muskingum K 根据 lag_hours 给出初始建议。
- Muskingum X 默认 0.2。

这些参数只是初始建议，不等于率定结果，不能替代实测资料校准。

## demo_gee.yaml

如果 CHIRPS 降雨时间序列成功生成，HydroLite 会创建：

```text
cases/demo_gee.yaml
data_demo/gee/gee_subbasins.csv
data_demo/gee/gee_reaches.csv
```

然后可以运行：

```bash
python -m hydrolite validate cases/demo_gee.yaml
python -m hydrolite run cases/demo_gee.yaml
```

## 局限性

- 示例流域为小矩形，仅用于联动测试。
- bbox 面积是近似值，不替代正式 GIS 面积计算。
- GEE 数据统计依赖账号权限、Project 设置和数据集可用性。
- 参数建议没有经过率定。

后续开发路线：

1. 增加更多流域边界格式和投影检查。
2. 增加 GEE 导出任务管理。
3. 增加导出成果到 HydroLite/OpenHydroNet 输入格式的转换。
4. 在 Streamlit 中加入任务状态和数据目录管理。
