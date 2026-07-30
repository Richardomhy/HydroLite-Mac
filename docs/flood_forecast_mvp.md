# 洪水预测与多模型集合 MVP

历史回放与实时预报必须分开：hindcast 可使用完整历史事件评估模型，forecast 只可使用起报时刻已知信息。数据同化后的同一时刻结果是 analysis，其后的结果才是 forecast-from-analysis。真实适用性需按独立事件验证，参见 `multi_event_hindcast_validation.md`。

HydroLite Studio v0.7.0-dev 提供情景降雨、历史回放、HydroLite 物理成员、synthetic-demo 水库联算、可选本地 HEC-HMS、机器学习基线、可选 LSTM smoke test、集合分位数和阈值诊断。当前验证等级为 `synthetic_demo`，回放模式为 `hindcast_demo`，不是业务化洪水预警系统。

默认 Demo 生成 baseline、0.8/1.0/1.2 倍率、峰值提前和峰值推迟共 6 个成员。失败成员保留错误原因，不以零过程线替代。HydroLite 使用完整单位线和 Muskingum 退水尾部；HEC-HMS Reservoir 仍为 `blocked_gate`。

运行：

```bash
python -m hydrolite forecast run-demo
python -m hydrolite forecast validate output/flood_forecast
```

真实业务预测还需要实时预报降雨、连续水文状态、多事件独立验证、真实水库曲线、运行监控和人工审核。
