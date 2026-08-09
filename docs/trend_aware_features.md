# 因果趋势特征

M4 提供 lag、向后 rolling、稳健局地斜率、指数均值、季节基线/异常、差分、波动、近期百分位和缺失标记。

- forecast 只使用 `timestamp <= issue_time`。
- centered rolling 仅可在 `analysis_only=true` 的历史分析中使用。
- day-of-year 或 month 季节基线只在训练期拟合，保存 `fit_start`、`fit_end`、`sample_count` 和方法。
- validation/test 不参与季节基线拟合。

这些特征是透明的因果特征工程，不是论文网络复现，也不引入 BiLSTM。双向上下文不能用于真正未来预报。
