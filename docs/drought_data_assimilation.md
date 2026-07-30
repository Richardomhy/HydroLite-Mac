# Drought Data Assimilation

MVP 支持土壤水 nudging、流量 nudging 接口、水库储量替换、地下水状态更新和可选 EnKF 状态接口。结果明确区分 `analysis_state` 与后续 `forecast_state`。

同化引起的储量增减必须作为 `assimilation_adjustment` 写入账本，并在更新后执行非负与水量一致性检查。调整量不是自然降雨、蒸散或径流，不能隐藏。
