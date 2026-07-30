# 洪水预测输入协议

标准降雨字段为 `issue_time`、`valid_time`、`lead_time_hr`、`member_id`、`subbasin_id`、`precipitation_mm`、`interval_minutes`、`source`、`scenario_type`、`units` 和 `quality_status`。

`source` 只能明确标记为 observed、forecast、scenario、synthetic 或 model_generated。设计暴雨、倍率和移峰情景属于 scenario，不得标记为正式 forecast。时间步必须规则，降雨不得为负，issue time 之后的 valid time 用 lead time 表示。

状态协议可包含出口流量、库水位、库容、前期降雨、土壤湿度代理和基流。缺失状态保持缺失，不填零。
