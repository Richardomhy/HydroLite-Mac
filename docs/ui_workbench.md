# HydroLite Studio 工作台

HydroLite Studio 是 HydroLite-Mac 的项目化 Streamlit 界面。它把数据校验、情景运行、GEE 数据产品、SWMM 联动、OpenHydroNet-ready 输入包、结果对比和报告导出组织到同一个工作台中。

工作台不新增模型算法，不训练 OpenHydroNet，也不运行真实大规模 AI 推理。所有按钮调用现有 HydroLite CLI 或 Python API。

## 启动

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

浏览器访问：

```text
http://localhost:8501
```

默认项目路径为：

```text
projects/demo_project
```

如果 `project.yaml` 不存在，界面会提示先创建项目，不会自动覆盖已有项目。

## 页面说明

### 1. 项目首页

显示 `project.yaml` 概览、模块启用状态、情景数量、最近输出文件、`project_summary.md` 和已有项目包。可刷新项目状态、生成项目摘要并下载项目包。

### 2. 数据与校验

显示项目 cases 列表、项目校验结果、根目录 validation 输出、failed/warning 数量和校验报告。可校验当前项目或根目录全部情景。

### 3. 情景运行

选择项目情景，查看 YAML 内容，运行单情景或批量运行项目情景。页面显示主要输出、`batch_summary.xlsx` 和运行日志摘要。

### 4. GEE 数据中心

显示 GEE 初始化状态、支持数据集、GEE 输出摘要、CHIRPS 降雨、温度、参数建议和 GEE 到 HydroLite 报告。未认证或缺少 `GEE_PROJECT` 时会显示 next steps。

### 5. SWMM 联动

显示启用 SWMM 的项目情景、`swmm_summary.xlsx`、`swmm_kpis.xlsx`、`coupling_summary.xlsx`、节点水深、管道流量、系统过程线和关键图表。SWMM 运行失败时不影响 HydroLite 主流程展示。

### 6. OpenHydroNet AI 输入

显示 OpenHydroNet 环境状态、accelerator、smoke test 输出、静态属性、气象 forcing、观测流量、HydroLite 流量和输入质量报告。页面明确提示当前只是 OpenHydroNet-ready input package，不代表真实 AI 预测已经完成。

### 7. 结果对比

显示 `scenario_comparison.xlsx` 的 overview、hydrology、water balance、SWMM、coupling 和 performance metrics，并展示峰值流量、径流量、水量平衡和 SWMM KPI 图表。

### 8. 报告与导出

显示 `hydrolite_report.md`、`project_summary.md`、输出文件清单和项目包。可刷新项目报告并导出项目包。

### 9. 系统诊断

显示 Python、Git commit、运行目录、Streamlit 环境、关键依赖版本、GEE 诊断、SWMM 诊断和 OpenHydroNet 诊断。可运行 GEE、OpenHydroNet 和 Streamlit 本地诊断脚本。

## 推荐流程

1. 打开“项目首页”，确认项目路径和模块状态。
2. 进入“数据与校验”，运行项目校验。
3. 进入“情景运行”，先运行单情景，再批量运行项目情景。
4. 如果需要遥感辅助输入，进入“GEE 数据中心”生成 HydroLite 输入。
5. 如果使用排水管网联动，进入“SWMM 联动”检查 coupling 和 SWMM 输出。
6. 如果需要 AI 输入包，进入“OpenHydroNet AI 输入”生成 OpenHydroNet-ready package。
7. 进入“结果对比”生成并查看多情景对比。
8. 进入“报告与导出”生成报告和项目包。
9. 遇到环境问题时进入“系统诊断”查看依赖和后端状态。

## 本地版与云端版差异

本地版可以使用 macOS 隔离 SWMM 求解器环境、GEE 本地认证和外部 OpenHydroNet 仓库。云端版主要用于展示已有 demo 输出、校验结果、报告和轻量计算。

Streamlit Community Cloud 中：

- 不强制存在 `HYDROLITE_SWMM_PYTHON`；
- 不强制执行 GEE 浏览器认证；
- 不强制存在 OpenHydroNet 外部仓库；
- 后端不可用时页面应给出清晰提示而不是崩溃。

## 常见错误处理

- `project.yaml not found`：确认项目路径，或运行 `python -m hydrolite project create projects/demo_project`。
- GEE unavailable：设置 `GEE_PROJECT`，本地运行 `python scripts/gee_auth_local.py`。
- SWMM 后端 failed：本地设置 `HYDROLITE_SWMM_PYTHON`，或只查看已有输出。
- OpenHydroNet repo unavailable：保持输入包功能可用；外部仓库诊断不代表训练或预测已经启用。
- 输出文件 unavailable：先运行对应情景、batch、compare 或导出命令。
