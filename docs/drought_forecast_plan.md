# Drought Forecast Plan

## 目标

建立轻量干旱评估和预测骨架，支持水文项目中对降雨、径流和遥感指标的快速研判。

## 指标

- SPI / SPEI。
- 降雨距平。
- 土壤湿度或 GEE 遥感指标。
- 径流距平。
- 干旱等级。

## 第一阶段范围

先做指标计算、等级判定和报告，不做复杂气候模型，不训练 AI。

## 输出

- drought_indices.csv。
- drought_level_summary.xlsx。
- drought_forecast_report.md。

## 风险

干旱指标需要足够长的历史序列，短 demo 数据只能展示格式，不能作为真实气候结论。
