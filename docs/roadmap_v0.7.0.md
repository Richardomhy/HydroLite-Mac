# HydroLite Studio v0.7.0 Roadmap

## 总目标

v0.7.0 的目标是把 v0.6.0-beta.1 已经稳定的项目工作台继续推进到“真实项目准备与 GIS 协同”阶段：让用户更容易从 QGIS、Excel/CSV、GEE 和已有工程资料进入 HydroLite，再输出可复核的校验、率定和报告成果。当前 QGIS 方向仍是 `qgis_process` / GeoJSON 文件级自动化，不是完整 QGIS 插件；QGIS 转项目工作流见 `docs/qgis_project_workflow.md`。

本轮 `0.7.0-dev` 先新增全流程工作流总控架构，统一描述数据模板、QGIS 预处理、流域划分、GEE 输入、HydroLite 模拟、HEC-HMS、SWMM、洪水/干旱预测、率定、对比、报告和用户手册阶段。它提供 dry-run 计划、阶段状态和报告文件，不一次性实现所有模型功能。

## 与 v0.6.0-beta.1 的关系

v0.6.0-beta.1 是当前稳定 beta，已经包含项目工作流、数据模板、项目向导、教程、报告导出、GEE/SWMM/OpenHydroNet-ready 输入包和 beta 反馈闭环。v0.7.0 是开发规划，不代表这些能力已经发布。

## 重点功能

1. GIS / QGIS Bridge：QGIS 图层导出 HydroLite 模板、流域/河网/边界导入、结果回写、`qgis_process` 与 PyQGIS 诊断；第一步是 qgis_process / GeoJSON 文件级 Bridge MVP，不是完整插件。
2. 真实项目导入增强：Excel 导入、批量 CSV 检查、字段映射、单位转换、错误定位到行列。
3. 模型率定与参数敏感性：CN、lag_time、Muskingum K/X 轻量扰动，NSE/RMSE/KGE 指标对比，自动率定报告。
4. 报告模板增强：Word 样式模板、中文工程报告、图表标题、表号、目录、封面和免责声明。
5. 桌面版准备：PySide6/Tauri/Electron/本地启动器评估，一键打开 Streamlit，macOS 打包验证。
6. QGIS / SWAT / GEE 协同：SWAT 项目目录关系、GEE basin boundary 与 QGIS 边界互转、HydroLite 作为前处理和快速评估工具。
7. 全流程工作流引擎：阶段注册、模板化计划、dry-run、状态文件和 Streamlit 统一入口。
8. 流域划分 MVP：后端诊断、合成 DEM、QGIS 填洼和可识别的 fallback 产物；当前为 `partial`，不等于专业 GIS 划分能力。

## 不做什么

- 不替代 MIKE、SWMM、SWAT+、ANUGA 或 QGIS。
- 不训练 OpenHydroNet。
- 不运行真实大规模 AI 推理。
- 不做复杂全局优化率定。
- 不把外部仓库、secrets、credentials、模型权重纳入版本库。
- 不把 QGIS Bridge 诊断等同于完整 QGIS 插件。
- 不把 `planned` 或 `partial` 阶段宣传为已经可用的完整模型功能。

## 推荐开发顺序

1. M1：先做 QGIS 可行性诊断，确认 macOS 路径、命令行和隔离环境；此阶段不开发完整 QGIS 插件。
2. M2：做 Excel/CSV 导入增强，因为这是普通用户最直接的入口。
3. M3：在已有观测流量评估基础上做轻量参数扫描。
4. M4：增强报告模板，让输出更接近工程交付材料。
5. M5：评估桌面启动器，不急于重写 Streamlit。
6. M6：整理 v0.7.0-beta 发布包和验证清单。

## 风险

- QGIS/PyQGIS 在 macOS 上路径与 Python 环境差异大。
- Excel 字段映射容易变成复杂 ETL，需要守住最小模板化能力。
- 参数扫描可能被误解为自动率定，需要明确范围和免责声明。
- Word/PDF 样式依赖可能带来跨平台渲染差异。
- 桌面打包可能放大依赖问题，应先做启动器验证。

## 验收标准

- 所有新增能力都有 CLI 或 Streamlit 入口。
- 所有真实项目导入路径都先校验，不直接修改 `data_raw`。
- QGIS 相关功能可在无 QGIS 环境下给出清晰诊断。
- 流域划分 MVP 在后端不完整时不崩溃，fallback 产物明确标记且通过 HydroLite 数据模板校验。
- 轻量率定输出参数、指标、图表和报告。
- 报告模板能生成可交付的中文示例报告。
- `pytest -q`、healthcheck、smoke test 通过。

## v0.7.0-dev 工作流引擎验收

- `python -m hydrolite workflow list` 能列出所有阶段及状态。
- `python -m hydrolite workflow plan templates/workflows/full_modeling_workflow.yaml output/workflow_plan` 能生成 dry-run 计划。
- `python -m hydrolite workflow run-full projects/demo_project --dry-run` 只写计划、状态和报告，不执行长任务。
- Streamlit `全流程工作流` 页面能展示阶段、输入、输出和 planned/partial/available 区分。
- HEC-HMS、洪水预测、干旱预测和用户手册导出在未实现前保持 planned；流域划分仅以 MVP `partial` 状态开放。
