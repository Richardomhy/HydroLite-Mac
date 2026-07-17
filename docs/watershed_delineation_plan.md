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

## 当前 MVP 进展

v0.7.0-dev 已实现 `hydrolite.watershed` 诊断和小型 DEM 处理 MVP：可探测 qgis_process / GRASS / SAGA / Whitebox / TauDEM 候选算法，生成合成 DEM，优先运行 QGIS 填洼与 D8 流向，并使用 HydroLite 无环拓扑算法稳定完成汇流累积和河网提取。出口点流域边界目前仍为明确标记的 fallback，同时生成 HydroLite CSV。

当前 Mac 上的 QGIS 3.44.10 虽加载了 `grassprovider`，但 QGIS app、PATH、`/Applications/GRASS*.app` 和 Homebrew 常见位置均未发现 GRASS runtime，且没有有效 `GISBASE`。因此 GRASS 算法描述存在，但 `r.watershed` 等算法无法注册执行。该问题不会阻断当前稳定 D8 链路。

该能力状态为 `partial`，不代表专业流域划分已完成。详见 `docs/watershed_delineation_mvp.md`。

## 风险

DEM 坐标系、出口点位置、平坦区处理、阈值选择和大 DEM 性能都会影响结果，需要明确日志和报告。

## 下一阶段

- 引入稳定的出口点划分后端，并用真实小流域继续验证现有汇流累积链路。
- 增加投影、单位、出口点吸附和面积一致性检查。
- 对真实小流域建立与 QGIS 人工结果的对照验收。
