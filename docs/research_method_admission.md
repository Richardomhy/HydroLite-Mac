# 方法借鉴准入

水质方法只有通过单位、时间、站点映射、上游方向、固定测试集和浓度/负荷分离门禁，才可进入实验。synthetic 结果只能标记为方法演示；Trend 未在验证集增加价值时不得强制保留；法定水质合规评价不属于 M5。

进入后续实验里程碑前，方法必须具备来源链接、许可证评估、明确“不复制”清单、独立基线、数据需求、泄漏门禁和局限性。准入只允许 clean-room 独立设计，不构成论文复现。

- Gamma 特征必须因果、非负，并不替代 HydroLite 水量账本。
- 图时序残差必须保留物理预测、订正和不确定度；双向时间模型仅用于历史分析。
- 水质实验仍是接口准备，主能力保持 `planned`。
- 易发性实验必须优先空间验证和监督基线；XAI 不解释为因果，RL 无独立增益时不得推荐。

`python -m hydrolite research validate` 会检查这些登记层门禁，不运行任何模型算法。

Gamma 的 M3 准入还要求：无噪声前向一致性满足 NSE/KGE/PBIAS 门槛、未来输入扰动不改变历史特征、合成基准使用固定独立测试窗口，并将真实数据增益保留为 `not_tested`。
# M4 admission gate

Graph, trend and multi-horizon methods may be marked `experimental` only after DAG, provenance, future-leakage, validation-only weighting and fixed-test comparison gates pass. Synthetic value added never upgrades real-data validation, and an absent improvement is recorded as `not_demonstrated`.
