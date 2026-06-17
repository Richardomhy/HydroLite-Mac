# HydroLite Studio v0.6.0-beta 发布说明

HydroLite Studio v0.6.0-beta 已进入 beta 测试阶段。本版本重点不是新增模型算法，而是把 HydroLite 从命令行 MVP 扩展为一个以“项目”为中心的轻量水文水动力工作台。

## 在线体验

https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app

## GitHub 仓库

https://github.com/Richardomhy/HydroLite-Mac.git

## 推荐体验流程

```text
教程与 Demo -> 数据模板 -> 项目向导 -> 数据与校验 -> 情景运行 -> GEE 数据中心 -> SWMM 联动 -> OpenHydroNet AI 输入 -> 结果对比 -> 报告与导出
```

## 适用对象

- 希望快速理解 HydroLite Studio 工作流的水文、水动力和城市排水学习者；
- 需要准备真实项目 CSV/GeoJSON 输入模板的用户；
- 需要演示项目创建、情景运行、结果对比和报告导出的团队；
- 希望在本地探索 GEE、SWMM coupling、OpenHydroNet-ready 输入包的研究者。

## v0.6.0-beta 包含

- 项目工作流；
- Streamlit 专业工作台；
- 项目向导；
- 真实项目数据模板与校验；
- 教程与 Demo 模式；
- Markdown / Word / HTML / PDF fallback 报告导出；
- GEE 数据中心；
- SWMM 联动；
- OpenHydroNet-ready 输入包；
- 观测流量评估；
- 项目打包导出；
- GitHub 与 Streamlit Cloud 部署说明。

## 当前限制

- 在线版适合演示和查看示例，不保证 GEE/SWMM/OpenHydroNet 后端完整可用；
- 本地版需要用户自行配置 GEE project、SWMM solver 或外部仓库；
- OpenHydroNet 当前不训练模型，不运行大规模推理；
- PDF 导出依赖可用后端，否则生成 fallback 说明；
- 真实工程结果需要专业人员复核。

## 后续计划

- 提升真实项目导入体验；
- 增强数据质量诊断；
- 增加更多工程报告模板；
- 改进云端演示数据与本地完整工作流的衔接。
