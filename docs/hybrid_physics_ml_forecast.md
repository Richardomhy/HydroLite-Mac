# 物理—数据驱动混合订正

混合模型优先采用“HydroLite/HEC-HMS 物理过程线 + 残差订正”，不以 LSTM 完全替代物理模型。订正后流量强制非负，并检查体积变化幅度。

真实观测不足时状态为 `unavailable_insufficient_data`；只运行原创 synthetic demo。如果用 HEC-HMS 模拟值作为目标，必须称为 cross_model_emulator 或 cross_model_correction，不能称为 observed residual correction。
