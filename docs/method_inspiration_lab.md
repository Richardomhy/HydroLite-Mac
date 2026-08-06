# HydroLite 水文环境方法借鉴实验室

本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，不构成原论文模型的精确复现。

实验室登记 Gamma 因果滞后、趋势图多提前期、水文物理图残差和洪水易发性/XAI 方法。它不保存论文全文、图表、代码或原始训练设置。HydroLite 物理水量账本始终独立保留；所有方法演示都明确为 synthetic demo，不能作为真实项目验证。

双向时序模式仅可用于 hindcast/reconstruction/gap-filling diagnosis。未来预报会主动阻断该模式。洪水易发性默认 spatial block CV；随机像元划分仅作为泄漏诊断。
