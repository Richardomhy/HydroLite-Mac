# Continuous Hydrology MVP

HydroLite 的事件模型以单场降雨为边界；连续模型按日推进冠层、地表、上下层土壤、地下水、河道和可选水库状态。状态不会在月末或年末重置，也不把若干独立事件拼接后称为连续模拟。

最小链路为：日气象质量检查 -> PET -> 截留/入渗 -> 土壤蒸散与渗漏 -> 壤中流/基流 -> 河道路由 -> 日与时期水量门禁。Demo 覆盖 2000–2019，明确标记 `synthetic_demo=true`，只验证软件流程。

```bash
python -m hydrolite continuous validate-config data_demo/drought/continuous_model_config.yaml
python -m hydrolite continuous run data_demo/drought/continuous_model_config.yaml
python -m hydrolite continuous validate output/drought_model/continuous
```

当前为透明的日尺度半分布式概念模型 MVP，不含完整雪过程、二维地下水、作物生长、水资源优化或业务预警。
