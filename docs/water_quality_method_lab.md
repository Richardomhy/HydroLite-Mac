# 多站点水质方法实验室

HydroLite Water Quality Method Lab 是 `partial` 实验能力，正式 `water_quality` 仍为 `planned`。本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，不构成原论文模型的精确复现。

## MVP 流程

观测 QC → 站点到河网映射 → 浓度/负荷账本 → HydroLite 水文、Gamma 和真实上游特征 → 1/3/7/14 日透明基线 → 验证集选模 → 固定测试集评价 → 报告和 bundle。

Trend 特征是可选候选项，不是必需项，也不会因单个指标有效而强制用于其他指标。14 日结果标记为 `long_horizon_diagnostic`，每个污染物和提前期单独评价。

## 明确边界

- synthetic demo 只验证软件方法，不代表真实水质预测。
- 不包含污染物反应方程、污染源清单模型或法定达标判定。
- 数据驱动订正不改变 HydroLite 水量账本。
- 测试集不参与特征、模型、正则化、权重或不确定性选择。
- 图特征只允许真实上游信息；下游和未来观测均被阻断。

运行：`python -m hydrolite water-quality-lab demo`。
