# Gamma 因果核

标准 Gamma 密度由正的 `shape` 和 `scale` 定义。解析平均滞后为 `shape × scale`；当 `shape > 1` 时，解析峰值滞后为 `(shape - 1) × scale`，否则峰值位于零附近。离散核使用时间区间中点采样并归一化，因此离散平均滞后可能与解析值略有差异。

特征采用有限支撑的零填充因果卷积：`feature[t]` 仅使用 `source[0:t]`。前期不重新归一化，避免改变核的体积含义；输出同时提供 `is_warmup`、`available_kernel_fraction` 和 `effective_history_length`。修改 `t+1` 之后的输入不能改变 `feature[:t+1]`。

所有 kernel 元素必须有限、非负且总和约为 1。组合权重允许从非负原始权重归一化，但会同时保存原始权重和归一化权重。
