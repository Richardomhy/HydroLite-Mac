# 产品状态与验证等级

产品状态为 `production_ready`、`ready_with_warnings`、`experimental`、`planned` 和 `unavailable`。验证等级为 `synthetic_demo`、`framework_ready`、`ready_with_warnings`、`real_data_tested`、`independently_validated` 和 `production_ready`。

“能运行”不等于“已经真实验证”。系统不会自动把 framework ready 升级为 real-data tested，也不会把 synthetic demo 升级为 ready with warnings。

当前必须保留的证据包括：Gamma 与 graph 仅有合成 value-added；trend 合成 value-added 未证明；水质方法实验总体 mixed 且真实数据未测试；洪水易发性推荐 Logistic，复杂模型未证明额外价值，XAI 重要性不稳定，RL 为 `rl_not_justified`。`water_quality` 仍为 planned；`flood_forecast` 和 `drought_forecast` 仍为 partial。

所有实验页统一展示真实项目独立验证缺失警告。易发性结果不得称为风险，XAI 不得解释为因果效应。
