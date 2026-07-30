# User Manual Export Plan

The unified data-center guides now document required uploads, supported formats, field meanings, units, authentication boundaries, quality states, lineage, model readiness, project creation and output export in Chinese and English.

## 目标

把现有 README、中文使用文档、教程、数据模板说明和故障排查整理为中英文用户手册。

## 中文用户手册

应覆盖安装、在线版、本地版、项目向导、数据模板、QGIS Bridge、GEE、SWMM、OpenHydroNet-ready 输入、结果对比、报告导出、FAQ 和故障排查。

## 英文用户手册

英文版优先覆盖安装、demo、project workflow、data templates、QGIS Bridge MVP、GEE/SWMM notes、report export 和 limitations。

## HEC-HMS / 洪水 / 干旱

这些章节在功能未实现前只能标记为 planned，不能写成可用教程。

## 导出形式

后续复用报告导出能力，生成 Markdown、Word、HTML 和 PDF/fallback。
# User Manual Plan

The manual will distinguish observed calibration, synthetic demo calibration, and HMS cross-model alignment. It will not describe alignment as flood prediction.

在“水量平衡审计”页面中，用户应以 full hydrograph 检查降雨、超额降雨、单位线、河段库容变化和出口体积；comparison window 仅用于与 HEC-HMS 的共同时间窗展示。

“洪水预测”页面提供预测就绪度、降雨情景、物理模型、ML/LSTM、水库、集合分位数、阈值和报告。页面中的 synthetic_demo、hindcast_demo、optional_local 和 blocked_gate 必须原样显示，避免误解为业务化预警。
