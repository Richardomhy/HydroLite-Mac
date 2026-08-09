# Gamma 参数可辨识性

M3 使用 SciPy 的有界最小二乘恢复单核 `shape`、`scale`、可选径流系数，以及多核各分量参数和非负归一权重。正参数使用对数变换，权重使用 NumPy softmax；这不是论文算法、MLE 复现或神经网络训练。

诊断状态包括 `well_identified`、`partially_identified`、`equifinal_good_response`、`weak_response` 和 `boundary_limited`。参数数值不同但过程线近似一致时，应报告等效性，而不能强称参数真实识别。

样本长度测试按时间顺序使用 100%、50%、25% 和 10% 训练窗口，测试窗口固定且不随机打乱。样本不足时返回 `insufficient_sample`，不会强行拟合。合成恢复只验证实现一致性，真实流域参数仍需独立观测与验证。
