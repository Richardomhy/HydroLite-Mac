# HydroLite Studio HEC-HMS 命令行运行探测与结果读取 MVP

## 目标与边界

本 MVP 用于识别 HEC-HMS 4.13 的命令行入口，生成可复用命令和脚本，并收集 stdout、stderr、日志和结果文件元数据。官方安装包 Castro 参考项目已通过 `Project.open` 和短时 `computeRun`；HydroLite 校准项目已通过 open 并识别 Run，但因降雨数据源门禁未满足而不自动计算。它不做 GUI 自动化，也不把 open 成功宣称为模拟完成。

当前 Mac 上 `/Applications/HEC-HMS-4.13.app/Contents/MacOS/HEC-HMS` 是 GUI 启动器。探测发现它不会可靠转发 `-script` 参数，而 app 内置 Java 17 可以直接通过 `hms.jar` 的 `hms.Hms -script` 模式执行短脚本。因此 HydroLite 的推荐命令使用 app 内置 Java，原生启动器只作为安装位置证据。

## 支持模式

- `dry-run`：默认行为，只写命令、脚本和运行报告，不启动 HEC-HMS。
- `probe`：执行只打印标记的临时 Jython 脚本，不打开项目、不运行模拟，最长 30 秒。
- `execute`：显式请求后执行生成的 Jython 项目脚本，最长 60 秒；成功退出也仍需人工检查模型日志和结果。
- DSS：只检测 `.dss` 文件是否存在，不读取 catalog 或时间序列，深度读取保持 `planned`。

## 命令行用法

```bash
python -m hydrolite hms cli-modes
python -m hydrolite hms run-command output/hec_hms_project
python -m hydrolite hms write-run-scripts output/hec_hms_project
python -m hydrolite hms run-probe
python -m hydrolite hms run output/hec_hms_project --dry-run
python -m hydrolite hms collect-outputs output/hec_hms_project
python -m hydrolite hms parse-logs output/hec_hms_project
python -m hydrolite hms run-summary output/hec_hms_project
python -m hydrolite hms validate-run output/hec_hms_project
```

可选真实尝试：

```bash
python -m hydrolite hms run output/hec_hms_project --execute --timeout 60
```

execute 不是默认操作。当前生成的 basin/met/control/run 语法尚未用官方项目逐项校验，因此不建议把 execute 返回码等同于工程模拟成功。

## 运行命令与脚本

`run-command` 返回 executable、args、cwd、安全环境覆盖、mode、confidence、warnings 和可复制命令。`write-run-scripts` 生成：

- `scripts/hydrolite_run_hms.py`：HEC-HMS Jython 脚本；
- `scripts/run_hms.sh`：macOS/Linux 脚本；
- `scripts/run_hms.bat`：Windows 命令模板。

脚本引用 `HydroLite_HMS_Project.hms` 和 `hydrolite_run`。项目名称、run 名称、时间序列存储和元素连通性仍须在 HEC-HMS 中复核。

## 日志与结果

每次 dry-run 或 execute 会生成：

- `reports/hec_hms_run_result.json`；
- `reports/hec_hms_run_report.md`；
- `reports/hec_hms_run_summary.xlsx`；
- `reports/hec_hms_run.log`；
- `reports/hec_hms_run_stdout.log`；
- `reports/hec_hms_run_stderr.log`。

日志解析搜索 `ERROR`、`WARNING`、`Simulation`、`Compute` 和 `DSS`。输出收集扫描 `.log`、`.out`、`.txt`、`.dss`、`.hms`、`run/` 和 `reports/`，只记录元数据，不深读大型结果。

## 常见失败原因

- 直接调用 macOS GUI 启动器时参数被忽略；
- app 内置 Java、`hms.jar` 或 native framework 不完整；
- Rosetta/x86_64 兼容性异常；
- 生成项目文件仍是 MVP 骨架，语法或模型元素不满足 HEC-HMS；
- run 名称不一致；
- 气象时间序列尚未映射到 HEC-DSS；
- 运行超时或日志中存在 ERROR。

## 下一步

1. 官方项目验证与日志见 `docs/hec_hms_official_validation.md`。
2. 生成项目格式门禁见 `docs/hec_hms_file_format_calibration.md`。
2. 将 HydroLite 参数映射与官方项目文件逐字段对照。
3. 验证一个小型项目能稳定生成 DSS。
4. 单独实现 DSS catalog 和流量过程读取，再接入情景对比报告。
# Rainfall-verified compute

The new `rainfall-compute` path is distinct from the legacy dry-run MVP. It executes only after the rainfall gate and reports success only with a completed `computeRun`, no fatal errors, a non-empty result DSS, and discovered flow pathnames. The 120-second process-group timeout remains mandatory.
