# 项目管理

使用 `python -m hydrolite projects register <workspace>` 注册真实工作区。项目 ID 使用随机安全短 ID，不直接使用项目名拼运行路径。

常用命令：`projects list`、`projects inspect`、`projects readiness`、`projects snapshot` 和 `projects archive`。

归档只改变注册记录。项目中心不会删除原始 workspace；项目快照只包含元数据和 manifest。
