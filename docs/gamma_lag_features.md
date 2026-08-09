# Gamma Lag Features

HydroLite Gamma Lag Features 借鉴公开研究中使用 Gamma 分布描述降雨—径流滞后的通用思想，由 HydroLite 独立设计，不构成原论文模型复现。

该组件把降雨、有效降雨或 HydroLite 已有径流分量转换成 derived feature。它不修改产流、汇流或水量平衡状态，也不把 quick、intermediate、slow 响应分量直接解释为真实地下水、壤中流或地表径流。

配置文件位于 `config/methods/gamma_lag_features.example.yaml`。`shape` 控制核的形状，`scale` 控制时间尺度，`support_length` 是有限历史窗口。示例参数带有 `synthetic_demo_defaults: true`，不是实际流域推荐值。

```bash
python -m hydrolite gamma kernel-demo
python -m hydrolite gamma truth-single
python -m hydrolite gamma truth-multi
python -m hydrolite gamma recover
python -m hydrolite gamma benchmark
python -m hydrolite gamma sample-efficiency
python -m hydrolite gamma report
```

合成真值用于验证前向一致性、因果性、参数恢复和基线比较。`synthetic_value_added=demonstrated` 不等同于真实项目有效，`real_data_value_added` 保持 `not_tested`。
