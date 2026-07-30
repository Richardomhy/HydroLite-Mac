# 本地任务队列

任务队列默认 FIFO、单并发，允许配置到 2。HEC-HMS、QGIS 和大型 GIS 默认按本地门禁串行运行。

命令包括 `tasks queue`、`run-once`、`run-until-empty`、`cancel`、`retry` 和 `logs`。

应用停止后，运行中的任务会在恢复检查中标记 interrupted；不会安装或启动常驻后台服务。
