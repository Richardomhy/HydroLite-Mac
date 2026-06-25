# qgis_process Bridge MVP

## 为什么选择 qgis_process

当前 HydroLite Python 环境下 PyQGIS 不可用，而本机已经检测到：

```text
/Applications/QGIS.app/Contents/MacOS/qgis_process
```

因此 v0.7.0 第一阶段采用 `qgis_process` 命令行桥接。它不需要把 PyQGIS import 到 HydroLite 主环境，风险更低，也更容易诊断。

## 当前 PyQGIS 不可用的原因

PyQGIS 通常绑定 QGIS.app 自带的 Python 与 Qt 环境。HydroLite 当前运行在独立 Python/conda 环境中，直接 `import qgis` 容易失败。MVP 阶段不强行混用两个 Python 环境。

## qgis_process 能做什么

- 检查 QGIS 版本；
- 列出 Processing 算法；
- 调用 Processing 算法处理矢量图层；
- 为后续 QGIS 图层导出 HydroLite 模板打基础。

## MVP 功能

- `qgis_process` 可用性检查；
- 算法列表预览；
- 示例 GeoJSON 图层信息读取；
- 示例矢量图层校验；
- 示例 GeoJSON 导出；
- 示例属性 CSV 导出；
- Streamlit 页面展示和下载 demo 输出。

本阶段不是完整 QGIS 插件。QGIS/GeoJSON 转换结果可以继续创建 HydroLite 项目，见 `docs/qgis_project_workflow.md`。

## CLI 用法

```bash
python -m hydrolite qgis version
python -m hydrolite qgis algorithms
python -m hydrolite qgis layer-info data_demo/gis/demo_subbasins.geojson
python -m hydrolite qgis validate-layer data_demo/gis/demo_subbasins.geojson
python -m hydrolite qgis export-vector data_demo/gis/demo_subbasins.geojson output/qgis_bridge_demo/demo_subbasins_export.geojson
python -m hydrolite qgis export-csv data_demo/gis/demo_subbasins.geojson output/qgis_bridge_demo/demo_subbasins_attributes.csv
python -m hydrolite qgis demo
```

## Streamlit 用法

打开 `QGIS Bridge` 页面：

- 运行 QGIS 诊断；
- 查看 `qgis_process --version`；
- 预览算法列表；
- 读取/校验示例图层；
- 导出示例 GeoJSON 和 CSV；
- 下载 demo report、summary、GeoJSON、CSV。

## 示例数据说明

示例数据位于：

```text
data_demo/gis/
```

包括：

- `demo_basin_boundary.geojson`
- `demo_reaches.geojson`
- `demo_subbasins.geojson`

这些文件使用虚拟坐标，不包含真实敏感位置。

## 后续如何扩展到 QGIS 图层导出 HydroLite 模板

1. 读取 QGIS 导出的 GeoJSON/GPKG；
2. 校验字段；
3. 映射到 `templates/data/` 中的 HydroLite 模板；
4. 输出 rainfall/subbasins/reaches/observed/SWMM mapping；
5. 在 Streamlit 项目向导中使用这些模板。

## 常见错误

- 找不到 `qgis_process`：运行 `python -m hydrolite qgis paths` 检查候选路径。
- `native:savefeatures` 失败：MVP 会对 GeoJSON 走 Python 标准库兜底。
- PyQGIS import 失败：当前属于预期，不影响 `qgis_process` 桥接。
- Streamlit Cloud 不可用：云端通常没有 QGIS.app。

## 与完整 QGIS 插件的关系

qgis_process Bridge 是文件和命令行层面的 MVP。完整 QGIS 插件可在后续阶段开发，但不应复制 HydroLite 模型算法，也不应绕过数据模板校验。

下一步的 GeoJSON 图层转 HydroLite 模板见 `docs/qgis_to_hydrolite_inputs.md`。
