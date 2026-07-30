# Continuous Calibration

连续率定只做有界轻量参数扫描，默认 30、最大 60 个候选，支持截留、入渗、土壤容量、渗漏、壤中流、地下水衰减、基流、路由 K/X 和 ET 系数。

时间序列按 calibration/validation/test 顺序切分，不随机打乱，不用测试期拟合 scaler 或分布。指标包括 NSE、log-NSE、KGE、RMSE、MAE、PBIAS、低流量、高流量和水量平衡惩罚。缺少足够实测流量时返回 `framework_ready_real_data_missing`，不声称完成真实率定。
