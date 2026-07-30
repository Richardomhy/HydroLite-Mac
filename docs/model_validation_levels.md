# 模型验证等级

- 无真实合格事件：`framework_ready_real_data_missing`
- 1–2 个：`limited_event_hindcast`
- 至少 3 个但无独立测试：`multi_event_hindcast_no_independent_test`
- 至少 5 个且有独立验证：`multi_event_validated`
- 至少 8 个且有独立测试：`multi_event_tested`

这些是软件诊断，不是工程验收。没有真实业务运行和正式预报输入时，不得标记 `operational_candidate` 或 `operational_verified`。
