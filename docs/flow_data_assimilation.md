# 流量数据同化

Flow Nudging 以 0–1 增益修正当前状态，并可设置衰减。输出始终区分 `open_loop`、`analysis` 和 `forecast_from_analysis`。analysis 使用了同化时刻观测，不能与纯预测结果混为一谈，gain 不得通过测试事件选择。
