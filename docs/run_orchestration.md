# 运行编排

在运行中心选择项目和 Recipe，先查看计划，再创建 Run。刷新页面不会自动创建新 Run，持久化的 `run_id` 用于恢复显示。

```bash
python -m hydrolite runs plan <project_id> data_preparation
python -m hydrolite runs create <project_id> data_preparation
python -m hydrolite runs start <run_id>
python -m hydrolite tasks run-until-empty
```

每个任务记录命令数组、依赖、timeout、日志、返回码和错误分类。
