# OpenHydroNet AI 洪水预测插件骨架

## 目标

OpenHydroNet AI 洪水预测板块用于未来接入基于 Google Research flood-forecasting 思路的河流洪水预测工作流。当前阶段只提供配置、适配器、诊断、占位运行和 Streamlit 入口。

## 与 Google Flood Hub 的关系

OpenHydroNet 的背景来自 google-research/flood-forecasting，与 Flood Hub 相关研究方向有关。本项目中的 OpenHydroNet 板块不是官方 Google 产品，也不代表 Google Flood Hub 服务，只是 HydroLite-Mac 的未来扩展接口。

## 依赖

未来真实推理通常需要 PyTorch 及相关科学计算依赖。当前骨架不安装大型依赖、不下载外部仓库、不训练模型。

## 输入数据需求

未来可能需要：

- 流域静态属性。
- 气象强迫数据。
- 观测流量。
- GEE 生成的地形、土地利用、水体和降雨特征。
- HydroLite/SWMM 生成的情景模拟结果。

## 与 HydroLite、GEE、SWMM 的关系

- HydroLite：提供水文模拟过程和情景管理。
- GEE：提供遥感和地理空间输入。
- SWMM：提供城市排水管网模拟结果。
- OpenHydroNet：未来用于 AI 洪水预测和多源结果对比。

## 阶段开发路线

1. 插件骨架和诊断脚本。
2. 隔离环境和示例推理。
3. GEE 输入特征接入。
4. 本地流域 schema 适配。
5. 与 HydroLite/SWMM 情景结果进行联合对比。
