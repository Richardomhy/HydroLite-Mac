# AI 洪水预测路线图

## Phase A：插件骨架

目标：

- 新增 GEE 数据中心和 OpenHydroNet 插件目录。
- 提供配置模板、诊断脚本、文档和 Streamlit 入口。
- 不接真实账号，不训练模型。

验收标准：

- 模块可 import。
- 诊断脚本可运行。
- 无 credentials 时不崩溃。
- 不修改 `data_raw`。

## Phase B：OpenHydroNet 环境接入与 smoke test

目标：

- 为 OpenHydroNet 建立隔离 Python 环境。
- 允许用户配置外部 OpenHydroNet 仓库路径。
- 只做最小 import、仓库路径、torch/MPS/CUDA 和配置 smoke test。
- 不训练模型，不下载大数据，不运行真实预测。

验收标准：

- 主 HydroLite 环境不被大型 AI 依赖污染。
- 失败时清晰记录环境缺失原因。
- 不影响 HydroLite/SWMM 主流程。
- 生成 `output/openhydronet/smoke_test_summary.xlsx` 和 `smoke_test_report.md`。

## Phase C：GEE 数据输入

目标：

- 增加 basin boundary 读取。
- 增加 DEM、降雨、土地利用、水体数据导出计划。
- 建立导出成果目录规范。

验收标准：

- 无账号时显示 unavailable。
- 有账号时可生成安全的导出任务计划。
- 不提交 secrets。

## Phase D：本地流域适配

目标：

- 将 HydroLite、GEE 和观测流量映射到 OpenHydroNet 输入 schema。
- 增加数据质量检查和时间对齐。

验收标准：

- 能输出 schema mapping 报告。
- 缺字段时有清晰错误。
- 可复用已有 validation 工作流。

## Phase E：与 HydroLite/SWMM 情景对比

目标：

- 将 AI 预测结果加入 `compare` 工作流。
- 与 HydroLite、SWMM、coupling、水量平衡结果共同展示。

验收标准：

- comparison workbook 增加 AI 预测 sheet。
- Streamlit 展示 AI 预测过程线和误差指标。
- 自动报告总结 AI 与物理模型差异。
