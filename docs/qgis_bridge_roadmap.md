# QGIS Bridge Roadmap

## 目标

QGIS Bridge 的目标是让 HydroLite 能与 QGIS 工程资料互通：从 QGIS 图层导出 HydroLite 数据模板，导入子流域、河网和流域边界，并把 HydroLite 输出结果回写到 QGIS 可读格式。

## 插件方式与 qgis_process 方式对比

| 方式 | 优点 | 缺点 | 建议 |
| --- | --- | --- | --- |
| QGIS 插件 | 用户体验最好，可在 QGIS 内操作 | 需要维护插件生命周期和 PyQGIS 兼容性 | v0.7.0 不优先 |
| `qgis_process` | 命令行清晰，适合 HydroLite 诊断 | 依赖本机 QGIS 路径 | 优先做可行性诊断 |
| 直接读写 GeoPackage/GeoJSON | 依赖少，适合模板导入导出 | 不能使用全部 QGIS 处理能力 | 最小可行方案 |

## macOS QGIS-LTR / QGIS.app 路径问题

macOS 上 QGIS 常见路径包括：

- `/Applications/QGIS.app`
- `/Applications/QGIS-LTR.app`
- app bundle 内部的 `qgis_process`

v0.7.0 应先做路径诊断，不假设用户安装位置。

## PyQGIS 环境隔离

PyQGIS 通常绑定 QGIS 自带 Python，不适合直接 import 到 HydroLite 主环境。推荐：

- 主环境不 import PyQGIS；
- 通过 subprocess 调用 QGIS 自带命令；
- 把诊断结果写入文本或 JSON；
- 失败时优雅提示。

## 与 HydroLite 数据模板的关系

QGIS Bridge 不直接绕过模板。它应生成或读取：

- subbasins CSV / GeoJSON；
- reaches CSV / GeoJSON；
- basin boundary GeoJSON；
- SWMM inflow mapping CSV；
- HydroLite 输出结果 GeoJSON 或 CSV。

## 最小可行方案

1. 诊断 `qgis_process` 是否可用。
2. 读取一个 GeoJSON 边界并校验几何类型。
3. 将子流域/河网图层字段映射到 HydroLite CSV 模板。
4. 将 HydroLite 结果 CSV 生成 QGIS 可加载的 CSV/GeoJSON。

## 暂不直接依赖第三方 ChatGPT/QGIS 插件的原因

- 第三方插件生命周期不可控。
- 插件可能引入额外账号、网络和隐私风险。
- HydroLite 当前目标是稳定的数据模板互通，不是把 AI 助手嵌入 QGIS。
- 最小命令行与文件格式桥接更容易测试和维护。
