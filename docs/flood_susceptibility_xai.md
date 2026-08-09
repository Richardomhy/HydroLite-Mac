# 洪水易发性 XAI

MVP 输出全局 permutation importance、partial dependence、局地扰动解释，以及模型间和空间块间的重要性稳定性。局地案例覆盖 TP、TN、FP 和 FN。

SHAP 是可选依赖；当前环境不可用时采用 permutation importance、PDP 和局地扰动回退。任何重要性或局地贡献都只描述统计关联，不表示因果效应。解释不稳定时必须保留不确定性提示。

强化学习未实现。静态易发性分类没有真实状态转移、可干预动作与决策相关奖励时，门禁返回 `rl_not_justified`。这不是失败，而是避免把普通分类包装成无意义的强化学习。
