# 生产运行中心架构

macOS 原生壳只管理一个打包后端子进程，并通过 loopback 健康端点和 manifest 通信。runtime DB、日志、上传和结果均位于只读 App Bundle 之外；stale lock 只有在 PID 启动时间校验后才恢复。

HydroLite Studio 使用标准库 SQLite、本地 FIFO 队列和独立进程组形成生产运行中心 MVP，不依赖 Redis、Celery 或常驻服务。

流程：项目注册 -> 数据就绪度 -> Recipe/Workflow 计划 -> Run -> Task -> Artifact -> 校验 -> 快照与报告。

- 数据库默认位于 `~/.hydrolite/runtime/hydrolite_runtime.sqlite3`。
- 每个 Run 使用独立目录，不修改项目 `raw/` 或 `standardized/`。
- 外部命令使用参数数组和 `shell=False`，每个任务带 timeout。
- optional 失败保留警告并允许后续任务继续；required 失败阻断下游。
- 当前状态为 `partial`，不是多用户服务器或分布式调度系统。
