# QGIS Bridge Diagnosis

## 为什么先做诊断

QGIS 在 macOS 上的安装路径、Python 环境和命令行工具位置差异很大。HydroLite v0.7.0 阶段先做可行性诊断，确认是否能连接 QGIS / QGIS-LTR / `qgis_process` / PyQGIS，再决定后续是否开发插件或自动化桥接。

本阶段只做 QGIS Bridge 可行性诊断，不等于已经实现完整 QGIS 插件。

诊断通过后，下一步 MVP 使用 `qgis_process` 做命令行桥接，详见 `docs/qgis_process_bridge.md`。

## macOS QGIS / QGIS-LTR 路径说明

常见路径包括：

- `/Applications/QGIS.app`
- `/Applications/QGIS-LTR.app`
- `/Applications/QGIS.app/Contents/MacOS/qgis_process`
- `/Applications/QGIS.app/Contents/MacOS/bin/qgis_process`
- `/opt/homebrew/bin/qgis_process`
- `/usr/local/bin/qgis_process`

诊断命令会扫描这些路径和 PATH 中的 `qgis_process`。

## qgis_process 与 PyQGIS 的区别

- `qgis_process`：命令行入口，适合 HydroLite 通过 subprocess 调用 QGIS 处理工具。
- PyQGIS：QGIS Python API，功能更强，但通常绑定 QGIS 自带 Python 环境，不适合直接混入 HydroLite 主环境。
- QGIS 插件：用户体验最好，但维护成本最高，应在诊断稳定后再评估。

## 如何解读诊断结果

运行：

```bash
python -m hydrolite qgis diagnose
```

输出：

```text
output/qgis/qgis_diagnosis.md
output/qgis/qgis_diagnosis.json
```

关注字段：

- `qgis_app_exists`
- `qgis_ltr_app_exists`
- `qgis_process_candidates`
- `qgis_process_version`
- `pyqgis_import`
- `recommendation`

## 推荐集成模式

优先级：

1. `qgis_process`：路径可执行且 `--version` 成功。
2. PyQGIS：候选 Python 能 import `qgis` 和 `PyQt5`。
3. QGIS 插件：QGIS app 存在，但命令行/PyQGIS 尚不可用。
4. 暂不可用：未检测到可用 QGIS 环境。

## 常见问题

- 有 `/Applications/QGIS.app` 但没有 `Contents/MacOS/bin/qgis_process`：尝试检查 `Contents/MacOS/qgis_process`。
- PyQGIS import 失败：通常是 QGIS Python 与 HydroLite Python 环境隔离导致。
- Streamlit Cloud 上不可用：云端一般没有桌面 QGIS，属于预期。
- 未安装 QGIS：诊断返回 warning，不影响 HydroLite 独立工作流。

## 后续插件开发计划

1. 先稳定 `qgis_process` 诊断。
2. 再做 GeoJSON/CSV 与 HydroLite 模板互转。
3. 最后评估 QGIS 插件壳，不复制 HydroLite 模型计算代码。
