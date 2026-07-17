# Watershed Delineation Plan

## 目标

为 HydroLite Studio 后续自动流域划分建立路线：从 DEM、出口点和边界生成河网、子流域和 HydroLite 输入模板。

## 核心步骤

1. DEM 输入。
2. 填洼。
3. 流向计算。
4. 汇流累积。
5. 河网提取。
6. 出口点校正。
7. 子流域划分。
8. 导出子流域、河道和边界。

## 可选路线

- QGIS Processing / GRASS GIS：适合与现有 qgis_process Bridge 合并。
- WhiteboxTools：命令行友好，适合本地自动化。
- TauDEM：专业但安装和 MPI 依赖可能更复杂。

## 第一阶段建议

先做 qgis_process / GRASS / WhiteboxTools 可用性诊断和小样例，不在当前步骤实现实际划分。

## 风险

DEM 坐标系、出口点位置、平坦区处理、阈值选择和大 DEM 性能都会影响结果，需要明确日志和报告。
