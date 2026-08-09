# 水质数据契约

核心变量为 `CODMn`、`NH3-N`、`TN`、`TP`，默认 canonical unit 为 `mg/L`。扩展变量包括 DO、水温、浊度、电导率、pH 和 TSS。

观测至少包含 `timestamp`、`station_id`、`variable_id`、`value`、`unit` 和来源。站点映射至少包含 `station_id`、`reach_id`、`mapping_method`、`mapping_confidence`。未解析站点不得进入图预测；最近河段 fallback 必须记为低置信度。

质量标记包括 `valid`、`suspect`、`invalid`、`below_detection_limit`、`missing`、`duplicate`、`unit_error`、`range_warning` 和 `stale`。suspect 保留在账本中，invalid 不进入训练。

非检出值默认 `preserve_qualifier`。只有显式配置时才允许 half detection limit、detection limit 或 missing，并必须写入 manifest。

模板位于 `templates/data_upload/water_quality_*`。所有输入必须保留单位、来源、时间和处理血缘。
