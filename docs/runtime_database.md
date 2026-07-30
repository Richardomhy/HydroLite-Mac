# 运行数据库

默认数据库：`~/.hydrolite/runtime/hydrolite_runtime.sqlite3`，schema version 1。

可使用 `HYDROLITE_RUNTIME_DIR` 或 `HYDROLITE_RUNTIME_DB` 定位隔离目录。表包含 projects、runs、tasks、dependencies、artifacts、logs、environments、connectors、settings 和 runtime events。

数据库不进入 Git。损坏时返回可读错误，不回显凭证。
