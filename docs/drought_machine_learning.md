# Drought Machine Learning

可选 scikit-learn 框架支持 persistence、climatology、linear regression、ridge、random forest 和 gradient boosting。目标可为 SPI/SPEI/SSI、土壤水/水库百分位和综合指数。

真实日尺度训练建议至少 3650 条、独立测试期至少 730 条；月尺度建议至少 10 年、测试期至少 2 年。划分按时间顺序，测试期不参与 scaler 拟合。数据不足返回 `insufficient_data`。

PyTorch 不自动安装。LSTM 建议至少 5000 个连续日或 15 年月记录；本步骤只提供接口和安全 Smoke，不训练真实模型。
