# Flood Forecast Plan

## 目标

在 HydroLite 模拟基础上建立轻量洪水预测工作流，用于情景预报、峰值流量估计和超警提示。

## 输入数据

- 降雨预报或情景降雨。
- 流域参数和河道参数。
- 既有 HydroLite / HEC-HMS / SWMM 输出。
- 可选观测流量和警戒阈值。

## 方法范围

第一阶段先做规则型预测：峰值流量、峰现时间、总量、阈值超限和预警等级。不训练深度学习模型，不运行大规模 AI 推理。

## 输出

- flood_forecast.csv。
- warning_levels.xlsx。
- flood_forecast_report.md。
- 峰值和阈值图。

## 与 HydroLite / HEC-HMS 的关系

HydroLite 提供快速情景模拟；HEC-HMS 后续可作为专业模型对照。洪水预测模块只消费这些模型的输出，不替代它们。
