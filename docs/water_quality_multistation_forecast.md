# 多站点水质预测实验

实验支持 persistence、seasonal climatology、站点本地线性、水文线性、Gamma 线性、上游加权、graph hydrology、graph Gamma 和 graph Gamma trend 九类透明候选模型。实现使用 NumPy 闭式线性拟合，不要求 sklearn、PyTorch 或 TensorFlow。

时间切分固定为 train、validation、test。候选选择只使用 validation RMSE；test 不参与模型选择。经验区间来自 validation residual，标记为 `empirical_validation_residual_interval`，不是正式概率预报。

图信息只从水文意义上的上游传播，travel-time shift 只把历史值推向未来目标时刻。任何 downstream 或 future observation 特征都会触发 leakage gate。

阈值指标仅为 `diagnostic_threshold` 的 recall、precision、F1 和 false alarm rate。阈值仅用于软件方法演示，不代表任何法律或管理标准。
