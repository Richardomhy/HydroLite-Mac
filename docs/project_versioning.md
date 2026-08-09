# HydroLite Project Versioning

HydroLite 的工作项目可以持续编辑；Project Version 是供运行和交付引用的不可变逻辑快照。创建版本不会修改、移动、清洗或复制覆盖原始数据。

## Version chain

版本号采用简单整数 `1, 2, 3...`。每个版本记录父版本、场景、数据快照、配置快照、HydroLite 版本、Git commit、SHA-256 和 provenance。工作副本变更不会改变旧版本；需要交付新内容时创建 N+1。

```bash
python -m hydrolite project version-create projects/demo_project --scenario demo
python -m hydrolite project versions projects/demo_project
python -m hydrolite project version-show <project_version_id>
```

## Data snapshot

默认 `referenced` 模式只读取文件元数据和内容 hash，记录逻辑路径、行数、时间范围、CRS、单位、质量和血缘。`metadata_only` 不承诺文件可移植；`portable` 只允许后续显式选择的小型数据。`data_raw` 永不默认打包。

## Configuration snapshot

配置快照记录 scenario、workflow、模型、参数、单位、运行选项、输入映射和数据要求。每个参数都有来源类型：`default`、`literature`、`calibrated`、`user_defined`、`derived`、`inherited` 或 `unknown`。未知来源必须显式保留，不能只保存 value。

## Run linkage

正式 Run 关联 Project Version、Data Snapshot、Configuration Snapshot、软件版本、Git commit 和脱敏环境快照。老 Run 标为 `legacy_unversioned`，可继续查看，但不能进入 approved deliverable。
