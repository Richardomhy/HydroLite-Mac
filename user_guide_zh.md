# HydroLite-Mac 中文使用文档

本文档面向 HydroLite-Mac 的本地使用、数据准备、情景运行、结果检查、情景对比和 Streamlit 可视化展示。HydroLite-Mac 是一个轻量级水文水动力 MVP 平台，支持 SCS-CN 产流、简化单位线汇流、Muskingum 河道汇流、水量平衡检查、SWMM 管网联动、批量情景运行和自动报告。

## 1. 项目结构

常用目录说明：

```text
hydrolite/                 核心 Python 包
cases/                     YAML 情景配置
data_demo/                 示例降雨、子流域、河道 CSV
data_raw/                  原始数据，只读，不应被运行过程修改
data_raw/swmm/demo.inp     SWMM 原始示例 INP，不直接修改
output/                    模型输出、校验结果、对比报告
docs/                      文档
streamlit_app.py           Streamlit Community Cloud 入口
requirements.txt           Python 依赖
```

重要约定：

- `data_raw/` 是原始数据区，不要把模型输出写入这里。
- SWMM 情景运行时会把 `data_raw/swmm/demo.inp` 复制到 `output/<case_name>/swmm/working.inp` 后再修改和运行。
- 所有结果默认写入 `output/`。

## 2. 本地环境安装

建议在项目根目录创建虚拟环境：

```bash
cd "/Users/minghenyu/Documents/hydrolite 模型"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

检查命令是否可用：

```bash
python -m hydrolite --help
python -m streamlit --version
```

## 3. 快速运行

完整本地流程：

```bash
python -m hydrolite validate cases/
python -m hydrolite run cases/demo.yaml
python -m hydrolite run cases/demo_swmm.yaml
python -m hydrolite batch cases/
python -m hydrolite compare output/
python -m streamlit run streamlit_app.py --server.headless true
```

浏览器访问：

```text
http://localhost:8501
http://127.0.0.1:8501
```

如果本地 Streamlit 打不开，可先诊断：

```bash
python scripts/diagnose_streamlit_local.py
```

诊断结果：

```text
output/streamlit_local_diagnosis.txt
```

## 4. 数据输入准备

### 4.1 降雨 CSV

现有示例文件：

```text
data_demo/rainfall.csv
```

当前 MVP 支持全流域统一降雨过程，典型字段：

```csv
time,rain_mm
2026-06-01 00:00,0
2026-06-01 01:00,0
2026-06-01 02:00,4
```

推荐字段：

- `time`：时间列，可被 pandas 解析。
- `rain_mm` 或 `rainfall`：降雨量，单位 mm。
- `subbasin_id`：可选。如果存在，会校验是否能匹配子流域表。

校验规则：

- 时间必须可解析。
- 降雨值不能为负。
- 如果提供 `subbasin_id`，不能为空，并应在子流域表中存在。

### 4.2 子流域 CSV

现有示例文件：

```text
data_demo/subcatchments.csv
```

典型字段：

```csv
id,area_km2,curve_number,lag_hours
S1,18.5,78,2.0
S2,11.2,84,1.5
```

字段说明：

- `id` 或 `subbasin_id`：子流域编号。
- `area_km2`：面积，单位 km2，必须大于 0。
- `curve_number` 或 `cn`：SCS-CN 曲线数，必须满足 `0 < CN <= 100`。
- `lag_hours`：滞后时间，单位小时，必须大于等于 0。

### 4.3 河道 CSV

现有示例文件：

```text
data_demo/reaches.csv
```

典型字段：

```csv
id,from,to,K_hours,X
R1,upper,middle,2.0,0.2
R2,middle,outlet,3.0,0.15
```

字段说明：

- `id` 或 `reach_id`：河段编号。
- `K_hours` 或 `k_hours`：Muskingum 参数 K，单位小时，必须大于 0。
- `X` 或 `x`：Muskingum 权重参数，必须满足 `0 <= X <= 0.5`。

稳定性条件：

```text
dt <= 2 * K * (1 - X)
dt >= 2 * K * X
```

其中 `dt` 使用小时，与 `K_hours` 保持一致。

### 4.4 SWMM INP

原始 SWMM 文件示例：

```text
data_raw/swmm/demo.inp
```

运行时不会直接修改该文件，而是复制到：

```text
output/<case_name>/swmm/working.inp
```

HydroLite-SWMM coupling 会把 HydroLite 的流量过程写入 `working.inp` 的 `[TIMESERIES]` 和 `[INFLOWS]` 段。

## 5. YAML 情景配置

基础情景示例：

```yaml
name: demo

model:
  time_step_hours: 1.0

inputs:
  directory: data_demo
  rainfall: rainfall.csv
  subcatchments: subcatchments.csv
  reaches: reaches.csv

outputs:
  directory: output/demo
```

SWMM 联动情景示例：

```yaml
name: demo_swmm

model:
  time_step_hours: 1.0

inputs:
  directory: data_demo
  rainfall: rainfall.csv
  subcatchments: subcatchments.csv
  reaches: reaches.csv

outputs:
  directory: output/demo_swmm

swmm:
  enabled: true
  inp_file: data_raw/swmm/demo.inp
  coupling:
    enabled: true
    source_flow_csv: output/demo_swmm/result_flow.csv
    source_time_column: time
    source_flow_column: outflow_cms
    target_node: J1
    inflow_name: HYDROLITE_INFLOW
    flow_unit: CMS
```

说明：

- `source_flow_csv` 如果尚未生成，校验器会给 warning，不作为 fatal error。
- `source_flow_column` 当前推荐使用 `outflow_cms`，它是 `result_flow.csv` 中的出口流量列。
- `target_node` 必须存在于 SWMM `working.inp` 中，否则 coupling 会失败，但 HydroLite 主流程仍会保留结果。

## 6. 运行前校验

校验单个情景：

```bash
python -m hydrolite validate cases/demo.yaml
python -m hydrolite validate cases/demo_swmm.yaml
```

校验整个目录：

```bash
python -m hydrolite validate cases/
```

输出文件：

```text
output/validation/validation_summary.xlsx
output/validation/validation_summary.csv
output/validation/validation_report.md
```

`validation_summary.xlsx` 包含：

- `overview`：每个情景的校验状态。
- `checks`：所有检查项。
- `errors`：fatal error。
- `warnings`：warning。

状态含义：

- `passed`：通过。
- `warning`：有警告但可继续运行。
- `failed`：存在 fatal error，应先修复。

## 7. 单情景运行

运行非 SWMM 情景：

```bash
python -m hydrolite run cases/demo.yaml
```

运行 SWMM 联动情景：

```bash
export HYDROLITE_SWMM_PYTHON="$(conda info --base)/envs/hydrolite-swmm-x64/bin/python"
python -m hydrolite run cases/demo_swmm.yaml
```

如果没有 `HYDROLITE_SWMM_PYTHON`，HydroLite 会优先尝试当前 Python 环境中的 SWMM 后端。即使 SWMM 后端失败，HydroLite 水文主流程仍会尽量保留可用输出，并在 `swmm_summary.xlsx` 中记录失败原因。

单情景输出：

```text
output/<case_name>/result_flow.csv
output/<case_name>/summary.xlsx
output/<case_name>/hydrograph.png
output/<case_name>/water_balance.xlsx
output/<case_name>/run.log
```

SWMM 情景额外输出：

```text
output/<case_name>/swmm/swmm_summary.xlsx
output/<case_name>/swmm/swmm_kpis.xlsx
output/<case_name>/swmm/node_depth_timeseries.csv
output/<case_name>/swmm/link_flow_timeseries.csv
output/<case_name>/swmm/system_timeseries.csv
output/<case_name>/swmm/coupling_summary.xlsx
output/<case_name>/swmm/working.inp
```

## 8. 批量情景运行

运行 `cases/` 下所有 `.yaml` 和 `.yml`：

```bash
python -m hydrolite batch cases/
```

批量输出：

```text
output/batch_summary.xlsx
```

字段包括：

- `case_file`
- `case_name`
- `status`
- `validation_status`
- `validation_message`
- `start_time`
- `end_time`
- `runtime_seconds`
- `output_folder`
- `peak_flow`
- `peak_time`
- `total_runoff_volume_m3`
- `water_balance_error_percent`
- `error_message`

如果某个情景校验失败，会标记为 `failed_validation`，不会运行该情景，但批量流程会继续处理其他情景。

批量运行结束后会自动生成情景对比结果。

## 9. 结果解读

### 9.1 result_flow.csv

典型字段：

- `time`：时间。
- `inflow_cms`：进入河道汇流系统的流量。
- `outflow_cms`：出口流量。

常见分析：

- 峰值流量：`outflow_cms.max()`。
- 峰现时间：峰值所在行的 `time`。
- 总出流体积：`outflow_cms` 按时间步积分。

### 9.2 summary.xlsx

记录基础运行指标，例如：

- `case_name`
- `time_step_hours`
- `rainfall_total_mm`
- `subcatchment_count`
- `reach_count`
- `peak_outflow_cms`
- `peak_outflow_time`
- `outflow_volume_m3`
- `swmm_status`

### 9.3 water_balance.xlsx

包含两个 sheet：

- `subbasin_balance`
- `outlet_balance`

重点字段：

- `total_rainfall_mm`
- `effective_rainfall_mm`
- `runoff_volume_m3`
- `routed_volume_m3`
- `balance_error_m3`
- `balance_error_percent`

如果 `balance_error_percent` 的绝对值超过 5%，日志和界面会给出 warning。

### 9.4 SWMM 结果

`swmm_summary.xlsx` 记录 SWMM 运行状态：

- `run_status`
- `backend_used`
- `error_message`
- `max_node_depth`
- `max_link_flow`
- `total_flooding_volume`
- `total_outflow_volume`
- `coupling_status`

`swmm_kpis.xlsx` 汇总 SWMM KPI。

`node_depth_timeseries.csv` 用于查看节点水深过程。

`link_flow_timeseries.csv` 用于查看管道流量过程。

`coupling_summary.xlsx` 用于检查 HydroLite 流量是否成功写入 SWMM 入流边界。

## 10. 情景对比与自动报告

手动生成对比：

```bash
python -m hydrolite compare output/
```

输出目录：

```text
output/comparison/
```

核心文件：

```text
output/comparison/scenario_comparison.xlsx
output/comparison/scenario_comparison.csv
output/comparison/hydrolite_report.md
```

图表：

```text
output/comparison/peak_flow_comparison.png
output/comparison/volume_comparison.png
output/comparison/water_balance_comparison.png
output/comparison/swmm_kpi_comparison.png
```

`scenario_comparison.xlsx` 包含：

- `overview`：情景是否有 HydroLite、水量平衡、SWMM、coupling 输出。
- `hydrology_metrics`：峰值流量、峰现时间、总径流量。
- `water_balance_metrics`：最大子流域水量误差、出口水量误差。
- `swmm_metrics`：SWMM 状态、后端、节点水深、管道流量等。
- `coupling_metrics`：coupling 状态、目标节点、入流名称、点数和总入流量。
- `missing_outputs`：缺失文件清单。

自动报告 `hydrolite_report.md` 会自动总结：

- 峰值流量最大的情景。
- 总径流量最大的情景。
- 水量平衡误差最大的情景。
- SWMM 最大节点水深、最大管道流量对应情景。
- coupling failed 情景。
- 所有情景是否成功。

## 11. Streamlit 可视化界面

启动：

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

界面功能：

- 扫描 `cases/` 情景文件。
- 选择并查看当前情景配置。
- 校验当前情景。
- 校验全部情景。
- 运行当前情景。
- 批量运行全部情景。
- 生成情景对比。
- 展示已有输出结果。

主界面展示：

- 情景名称。
- 输入数据路径。
- 水文方法。
- 汇流方法。
- 输出目录。
- 校验状态。
- `result_flow.csv` 表格和出口流量过程线。
- 峰值流量、峰现时间、总出流体积。
- 水量平衡表。
- SWMM 输出、KPI 和过程线。
- 批量汇总。
- 情景对比表和图。

侧栏会显示：

- 是否检测到 `HYDROLITE_SWMM_PYTHON`。
- 是否处于 Streamlit Cloud 环境。
- 当前项目根目录。

## 12. Streamlit Community Cloud 部署

GitHub Pages 不能运行 Streamlit/Python 服务。推荐方式是：

```text
GitHub 托管代码 + Streamlit Community Cloud 运行应用
```

Streamlit Cloud 配置：

- Repository：你的 GitHub 仓库，例如 `Richardomhy/HydroLite-Mac`
- Branch：`main`
- Main file path：`streamlit_app.py`
- Python version：建议 `3.11`

部署注意：

- 云端通常没有 macOS 隔离 SWMM 环境。
- 如果云端 SWMM 二进制包不可用，界面仍可展示已有输出、校验结果、批量汇总和情景对比。
- 非 SWMM 的 HydroLite 水文流程不依赖 SWMM 后端。

## 13. 常见问题

### 13.1 Streamlit 打不开

先运行：

```bash
python scripts/diagnose_streamlit_local.py
```

再尝试：

```text
http://localhost:8501
http://127.0.0.1:8501
```

### 13.2 validate 有 warning 是否能运行

可以。warning 表示建议检查，但不是 fatal error。比如当前 demo 使用全域降雨，没有 `subbasin_id`，校验器会提示 warning，但模型可以运行。

### 13.3 SWMM failed 是否影响 HydroLite 主流程

通常不影响。HydroLite 会继续生成主流程输出，并把 SWMM 后端失败原因写入：

```text
output/<case_name>/swmm/swmm_summary.xlsx
```

### 13.4 如何保护原始数据

不要把输出目录设置到 `data_raw/` 内。默认输出到：

```text
output/<case_name>/
```

SWMM 原始 INP 只读，运行时只修改复制后的：

```text
output/<case_name>/swmm/working.inp
```

## 14. 推荐工作流

### 14.1 新建一个普通水文情景

1. 准备降雨、子流域、河道 CSV。
2. 在 `cases/` 中复制一个 YAML。
3. 修改 `name`、输入文件和输出目录。
4. 运行校验：

```bash
python -m hydrolite validate cases/<your_case>.yaml
```

5. 运行模型：

```bash
python -m hydrolite run cases/<your_case>.yaml
```

6. 查看 `output/<case_name>/`。

### 14.2 新建一个 SWMM 联动情景

1. 准备或引用 SWMM `.inp` 文件。
2. 在 YAML 中启用 `swmm.enabled`。
3. 配置 `swmm.coupling`。
4. 校验：

```bash
python -m hydrolite validate cases/<your_swmm_case>.yaml
```

5. 运行：

```bash
python -m hydrolite run cases/<your_swmm_case>.yaml
```

6. 检查：

```text
output/<case_name>/swmm/coupling_summary.xlsx
output/<case_name>/swmm/swmm_summary.xlsx
```

### 14.3 多情景比较

1. 确保多个情景已有输出。
2. 运行：

```bash
python -m hydrolite batch cases/
python -m hydrolite compare output/
```

3. 查看：

```text
output/comparison/scenario_comparison.xlsx
output/comparison/hydrolite_report.md
output/comparison/*.png
```

