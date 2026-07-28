# HydroLite--HEC-HMS 跨模型对齐

HEC-HMS 出口过程线是模型参考，不是实测流量。HydroLite 对其拟合的正确术语为 **cross-model alignment**，不构成真实工程率定、洪水预报或验收结论。

该 MVP 仅使用精确时间戳匹配，不用缺失值填零，也不对 HMS 或 HydroLite 原始过程线插值。报告同时展示基准与最佳候选的峰值、峰现时间、体积、RMSE、MAE、NSE、KGE、PBIAS、R2，任何变差指标都会保留。

输出位于 `output/hec_hms_alignment_best/`，包括 `best_alignment_report.md`、指标表和清单。原 DSS、官方示例与 HEC-HMS 安装目录不会被修改或纳入 bundle。
