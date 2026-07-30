# 模型注册表

`hydrolite.model_registry` 统一记录模型中英文名称、领域、模型族、实现、状态、依赖、输入输出、训练/率定要求、不确定性、水库与预测支持、限制、文档和版本。

当前 HydroLite 事件模型为 available；HEC-HMS 事件模型为 available_local；HydroLite 水库为 available_demo；HEC-HMS Reservoir 为 blocked_gate。scikit-learn 和 PyTorch 模型根据本机依赖及数据门禁降级。

未来水环境模型通过同一注册表和数据协议接入；本版本不实现污染物输移、水温、DO 或营养盐反应动力学。
