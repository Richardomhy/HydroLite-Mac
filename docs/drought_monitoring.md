# Drought Monitoring

当前状态分别评估 meteorological、agricultural、hydrological、reservoir、groundwater 和 composite drought。

每次结果记录 `analysis_date`、`data_as_of`、`latest_observation_date`、latency、missing_sources 和 confidence。超过配置时效的输入标记 `stale_data`，不得称实时状态。

这是诊断与项目分析功能，不是法定干旱预警发布系统。
