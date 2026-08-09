# 水质浓度与负荷

浓度、负荷和通量是不同对象。`mg/L` 不能直接当作 `kg/day`。

MVP 的标准换算为：

```text
load_kg_day = concentration_mg_l × flow_m3_s × 86.4
```

负荷账本保留浓度来源、流量来源、时间对齐方法、容差、插值方法、单位换算和结果质量。没有流量时 `load_status=unavailable`，绝不使用浓度代理负荷。

水质和流量支持 exact、nearest with tolerance 与 daily aggregation。预测特征不得读取 issue time 之后的流量或水质观测。浓度指标良好不代表负荷指标良好，两类结果独立报告。
