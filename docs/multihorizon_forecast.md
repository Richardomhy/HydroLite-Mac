# 透明多提前期预测基础

M4 支持 `persistence`、`direct`、`recursive` 和 `direct_recursive_hybrid`，默认 horizon 为 1、3、6、12 个时间步。基础模型使用 NumPy 闭式线性/岭式回归，不强制依赖 scikit-learn 或 PyTorch。

## 安全门禁

- direct 为每个 horizon 独立建模。
- recursive 在 issue time 冻结真实历史，之后只能使用自身预测，禁止偷用未来 observation。
- hybrid 权重只由 validation period 选择；权重非负、和为 1，测试集不参与选择。
- 每个 horizon 单独报告 NSE、KGE、RMSE、MAE、PBIAS、R2、峰值、时序和体积误差，并报告 skill/error/bias/variance growth。

模型比较固定测试期，不因某个方法未提升而调整 synthetic demo。真实项目价值状态保持 `not_tested`。
