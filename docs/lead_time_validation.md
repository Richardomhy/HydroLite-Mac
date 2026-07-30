# 多提前期验证

默认检查 1、3、6、12 小时提前期，对比 open-loop、从 analysis 出发的 assimilated forecast 和 persistence。事件长度不足时跳过对应提前期；每个提前期分别保存 NSE/KGE/PBIAS、峰值与时序误差，不将 analysis 时刻拟合表现计入纯预报能力。
