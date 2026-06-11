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
```

输出：

```text
output/gee/gee_data_plan.xlsx
output/gee/gee_summary.xlsx
output/gee/gee_summary.csv
output/gee/gee_report.md
```

后续开发路线：

1. 增加更多流域边界格式和投影检查。
2. 增加 GEE 导出任务管理。
3. 增加导出成果到 HydroLite/OpenHydroNet 输入格式的转换。
4. 在 Streamlit 中加入任务状态和数据目录管理。
