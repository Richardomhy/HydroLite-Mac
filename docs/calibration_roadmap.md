# Calibration Roadmap

## 为什么需要率定

HydroLite 当前已经能导入观测流量并计算模型评估指标。v0.7.0 的率定目标是帮助用户理解参数对结果的影响，而不是替代专业率定软件。

## 第一阶段只做轻量参数扫描

第一阶段只做小范围参数扰动：

- 单因素扫描；
- 小规模组合扫描；
- 固定步长；
- 明确最大运行次数；
- 输出指标对比和推荐候选。

不做复杂自动优化、遗传算法、贝叶斯率定或大规模并行搜索。

## 支持参数

- SCS-CN：`cn`
- 简化单位线：`lag_hours`
- Muskingum：`k_hours`
- Muskingum：`x`

## 支持指标

- NSE；
- RMSE；
- KGE；
- 峰值流量误差；
- 峰现时间误差；
- 总量误差。

## 输出文件

建议输出：

- `calibration_results.csv`
- `calibration_summary.xlsx`
- `calibration_metric_comparison.png`
- `calibration_best_candidates.csv`
- `calibration_report.md`

## 风险

- 参数范围过大导致运行时间增加。
- 观测流量缺失或时间不对齐会导致指标不可比。
- 用户可能把轻量扫描误认为自动最优率定。
- 参数之间存在相互作用，单因素结果不代表全局最优。

## 不做复杂自动优化

v0.7.0 不做复杂优化。若后续确实需要，应单独设计：

- 优化算法；
- 参数边界；
- 约束；
- 计算预算；
- 不确定性分析；
- 工程审核流程。
