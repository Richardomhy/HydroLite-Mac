# 方法卡与准入状态

方法卡将来源思想转为 HydroLite 的独立接口契约：输入、输出、时间/空间尺度、因果和物理约束、比较基线、风险及下一里程碑。它不是算法实现或性能声明。

当前卡片只可处于 `method_card_complete` 或 `clean_room_ready`，且 `value_added_gate=not_tested`。因此任何 future 版本均须先完成独立验证，才能声称有附加价值。`physics_graph_temporal_residual` 明确阻止双向模型用于真实未来预测；水质卡也不改变 `water_quality=planned`。

M3 后，`gamma_lag_hydrologic_prior` 可标记为 `experimental`，但必须同时保留 `validation_required=true`、`synthetic_value_added` 与 `real_data_value_added=not_tested`。这只表示独立的 Gamma Lag Features 已通过合成软件门禁，不代表论文复现或真实流域验证。

使用 `python -m hydrolite research methods` 或 `python -m hydrolite research method <method_id>` 浏览记录。
# M4 foundation status

- `physics_graph_temporal_residual`: directed graph foundation implemented; no deep graph model; real validation required.
- `trend_graph_multihorizon_water_quality`: causal trend and transparent multihorizon foundations implemented; water-quality model not implemented.
- Both remain `experimental` with `validation_required=true`.

本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，不构成原论文模型的精确复现。
