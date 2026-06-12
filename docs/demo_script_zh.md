# HydroLite Studio v0.5.0-alpha.2 中文演示脚本

## 演示目标

用 10 到 15 分钟展示 HydroLite Studio 如何以“项目”为中心完成数据校验、情景运行、GEE 数据查看、SWMM 联动、OpenHydroNet 输入包、结果对比和报告导出。

## 开场介绍

“HydroLite Studio 是一个轻量级本地水文水动力建模工作台。当前版本 v0.5.0-alpha.2 面向公开演示，重点展示项目化工作流，而不是替代 MIKE，也不执行真实大规模 AI 预测。”

## 1. 启动工作台

```bash
python -m hydrolite version
python -m hydrolite healthcheck
python -m streamlit run streamlit_app.py --server.headless true
```

打开 `http://localhost:8501`，确认侧边栏显示 HydroLite Studio 和当前项目路径。

## 2. 项目首页

选择或确认项目路径：

```text
projects/demo_project
```

讲解：

- 项目名称、项目 ID、情景数量；
- 模块启用状态；
- 最近输出文件；
- `project_summary.md`；
- 项目包下载入口。

强调安全边界：`data_raw/` 不会被模型运行修改。

## 3. 数据与校验

点击“校验当前项目”。讲解：

- YAML 和 CSV 在运行前被检查；
- fatal error 会阻止运行；
- warning 会保留但不阻断演示；
- 校验结果可下载为 Excel 和 Markdown。

## 4. 情景运行

选择 `demo_gee.yaml`，查看 YAML 内容，然后点击“运行选中情景”。

展示：

- `result_flow.csv`；
- `summary.xlsx`；
- `water_balance.xlsx`；
- hydrograph；
- 运行日志摘要。

然后点击“批量运行项目情景”，展示 `batch_summary.xlsx`。

## 5. GEE 数据中心

展示 GEE 状态、支持数据集、CHIRPS 降雨、温度、参数建议和报告。

说明：

- 如果未配置 GEE_PROJECT 或未认证，页面会给出 next steps；
- 不提交任何 Google credentials。

## 6. SWMM 联动

选择 SWMM 情景，展示：

- `swmm_summary.xlsx`；
- `swmm_kpis.xlsx`；
- `coupling_summary.xlsx`；
- 节点最大水深图；
- 管道最大流量图。

说明：原始 `data_raw/swmm/demo.inp` 不被修改，系统只修改输出目录中的 `working.inp`。

## 7. OpenHydroNet AI 输入

展示 OpenHydroNet 环境状态和输入包文件：

- `static_attributes.csv`；
- `meteorological_forcing.csv`；
- `observed_streamflow.csv`；
- `hydrolite_streamflow.csv`；
- `input_quality_report.xlsx`。

必须说明：当前是 OpenHydroNet-ready input package，不代表已经完成真实 AI 模型预测。

## 8. 结果对比

点击“生成项目对比”，展示：

- overview；
- hydrology_metrics；
- water_balance_metrics；
- swmm_metrics；
- coupling_metrics；
- performance_metrics；
- 对比图表。

## 9. 报告与导出

点击“导出项目包”。展示：

```text
projects/demo_project/reports/demo_project_package.zip
```

收尾说明：该包用于演示和交付，不包含 secrets、external 仓库或模型权重。

## 结束语

“v0.5.0-alpha.2 的目标是把 HydroLite-Mac 从命令行原型推进到可演示的专业软件工作台。下一阶段可以继续增强真实数据接入、参数率定、工程化报告和更完整的水动力后端。”
