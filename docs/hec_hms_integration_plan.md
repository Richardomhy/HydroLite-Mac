# HEC-HMS Integration Plan

## 集成目标

让 HydroLite Studio 后续能够把 QGIS、GEE 和 HydroLite 数据模板整理为 HEC-HMS 可用项目，并在本地环境可用时运行 HEC-HMS、读取结果和纳入对比报告。

## 为什么优先采用命令行 / 项目文件桥接

HEC-HMS 是成熟专业软件，直接 GUI 自动化脆弱且难以跨平台复现。优先路线是生成项目文件、调用命令行或批处理入口，再读取输出文件。

## Mac 环境可行性

macOS 上 HEC-HMS 的命令行能力、Java 依赖、DSS 工具链和文件路径需要先诊断。v0.7.x 第一阶段只做诊断和项目生成规划，不直接运行大型模拟。

## HEC-HMS 项目结构

- Basin model：流域、子流域、河道、汇流关系。
- Meteorologic model：降雨、气象输入和空间分布方式。
- Control specifications：开始时间、结束时间、计算步长。
- Simulation run：把 basin、meteorologic、control 组合成一次运行。

## 与 HydroLite 数据模板的映射

- `subbasins.csv` -> subbasin elements, area, loss/transform parameters.
- `reaches.csv` -> reach elements and Muskingum-like routing parameters where applicable.
- `rainfall_csv` / GEE CHIRPS -> meteorologic time series.
- `project.yaml` / case YAML -> control specifications and run metadata.

## 输入输出文件规划

输入侧先生成 HEC-HMS 项目目录、basin model、met model、control specs 和 run config。输出侧规划读取 hydrograph、peak flow、volume、run log 和 DSS 摘要。

## DSS 结果读取风险

DSS 读取依赖库和平台兼容性不稳定，尤其在 macOS 上需要独立诊断。若 DSS 读取失败，应保留 HEC-HMS 原始输出路径并优雅降级。

## 不做 GUI 自动化的原因

GUI 自动化对窗口焦点、语言、分辨率和版本高度敏感，不适合作为可复现工程流程。

## 阶段计划

第一阶段：诊断 HEC-HMS 可用性，生成最小项目文件。  
第二阶段：运行最小项目，读取基础 hydrograph 和指标。  
第三阶段：纳入 Streamlit、对比和报告导出。
