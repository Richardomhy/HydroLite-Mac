# GEE 数据中心插件骨架

## 目标

GEE 数据中心用于未来从 Google Earth Engine 获取遥感、DEM、土地利用、降雨、水体和植被指数等数据，为 HydroLite 水文建模和 OpenHydroNet AI 洪水预测提供输入支撑。

当前阶段只提供插件骨架、配置模板、诊断脚本和 Streamlit 展示入口，不连接真实账号，不启动浏览器认证，不提交密钥。

## 初始支持数据类型

- DEM：地形高程和地形衍生参数。
- landcover：土地利用/覆盖分类。
- precipitation：卫星或融合降雨。
- ndvi：植被指数。
- water_index：水体指数占位。
- surface_water：长期地表水产品。

## 本地认证方式

未来可支持：

- 本地 Earth Engine credentials。
- `GOOGLE_APPLICATION_CREDENTIALS` 指向 service account JSON。
- `GEE_PROJECT` 指定 Google Cloud 项目。
- 配置文件中的 `project` 字段。

当前代码只检测这些来源，不触发 `ee.Authenticate()`，也不强制网页登录。

## Streamlit Cloud Secrets 注意事项

Streamlit Cloud 可通过 secrets 管理敏感信息，但不要提交 `.streamlit/secrets.toml`。仓库中只允许提交 `.streamlit/config.toml` 这类非敏感配置。

## Secrets 安全规则

- 不提交 Google service account JSON。
- 不提交 API key、token、client secret。
- 不把 `.streamlit/secrets.toml` 加入 git。
- 不把真实账号路径写死到代码中。

## 后续开发路线

1. 增加真实但非交互式 GEE 初始化。
2. 增加 basin boundary 读取和投影检查。
3. 增加数据检索计划和导出任务管理。
4. 增加导出成果到 HydroLite/OpenHydroNet 输入格式的转换。
5. 在 Streamlit 中加入任务状态和数据目录管理。
