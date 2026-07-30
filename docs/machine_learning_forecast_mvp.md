# 机器学习洪水预测 MVP

当前真实项目只有一个 18 小时事件，`real_training_ready=false`，不得据此训练并宣传有效的随机森林、梯度提升或 LSTM。

核心环境始终支持 persistence 和 NumPy 线性回归。Ridge、随机森林、梯度提升依赖可选 scikit-learn。数据必须按时间顺序划分，禁止 shuffle；scaler 只能在训练集拟合；未来流量和未来未知信息不得进入特征。

原创 `demo_ml_timeseries.csv` 含 6 个合成事件，仅验证代码流程。默认门禁 500 个连续时间步、5 个事件和 1 个独立测试事件只是软件诊断阈值，不是科学充分性标准。
