# HydroLite Studio 教程与 Demo 模式

`教程与 Demo` 是 HydroLite Studio v0.6.0-dev 面向新用户的内置引导模式。它帮助用户不手动编辑 YAML，也能按步骤理解项目、数据校验、情景运行、GEE、SWMM、OpenHydroNet 输入包、结果对比和报告导出。

## 目的

- 给第一次打开 Streamlit 的用户一条明确路线；
- 区分在线演示版和本地完整版；
- 用 `projects/demo_project` 完成一次可讲解的软件演示；
- 用 checklist 检查每一步是否已有输出；
- 生成 `reports/demo_summary.md` 作为演示记录。

## 在线演示路线 A

适合 Streamlit Community Cloud：

1. 打开在线地址；
2. 进入 `教程与 Demo`；
3. 加载 `projects/demo_project`；
4. 按步骤浏览项目首页、GEE、SWMM、OpenHydroNet、结果对比和报告；
5. 下载已有报告或项目包。

在线版不会强制执行 GEE 认证、SWMM 后端或 OpenHydroNet 外部仓库。

## 本地完整演示路线 B

适合已安装本地环境的用户：

```bash
python -m hydrolite project validate projects/demo_project
python -m hydrolite project batch projects/demo_project
python -m hydrolite project compare projects/demo_project
python -m hydrolite report project projects/demo_project
python -m streamlit run streamlit_app.py --server.headless true
```

本地可进一步配置：

- `GEE_PROJECT` 用于真实 GEE 摘要；
- `HYDROLITE_SWMM_PYTHON` 用于隔离 SWMM 求解器；
- OpenHydroNet 外部仓库用于环境诊断和研究扩展。

## 工程交付演示路线 C

适合展示“从项目到交付件”：

1. 使用 `项目向导` 创建或解释项目；
2. 使用 `数据与校验` 检查输入；
3. 使用 `结果对比` 比较多情景；
4. 使用 `报告与导出` 生成 Word、HTML、Markdown 和项目包；
5. 在 `教程与 Demo` 生成 `demo_summary.md`。

## Demo 步骤

1. 认识 HydroLite Studio；
2. 加载 demo_project；
3. 校验项目；
4. 运行 demo_gee 情景；
5. 批量运行项目；
6. 查看 GEE 数据中心；
7. 查看 SWMM 联动结果；
8. 查看 OpenHydroNet AI 输入包；
9. 查看结果对比；
10. 生成 Word/HTML/Markdown 报告；
11. 导出项目包；
12. 理解在线版与本地版差异。

每一步都有页面位置、要做什么、预期结果、CLI 等价命令、在线版说明、本地版说明和成功文件检查。

## CLI 用法

```bash
python -m hydrolite tutorial list
python -m hydrolite tutorial checklist projects/demo_project
python -m hydrolite tutorial summary projects/demo_project
python -m hydrolite tutorial reset projects/demo_project
```

`reset` 只重置教程进度，不删除项目计算成果。

## 输出文件

```text
projects/demo_project/reports/demo_progress.json
projects/demo_project/reports/demo_summary.md
```

`demo_progress.json` 是运行产物，不纳入 git。

## 常见问题

- GEE 显示 unavailable：在线版或未认证本地环境是正常情况；本地设置 `GEE_PROJECT` 后再运行。
- SWMM 显示 failed/skipped：云端可能缺少二进制后端；本地建议使用隔离求解器。
- OpenHydroNet 没有真实预测：当前只准备输入包和环境诊断，不训练模型、不做大规模推理。
- PDF 报告不可用：仍会生成 Word、HTML、Markdown 和 PDF unavailable 说明。

## 下一步学习建议

- 从 `项目向导` 学习如何创建新项目；
- 从 `数据模板` 下载真实项目 CSV/GeoJSON 模板并校验输入数据；
- 从 `数据与校验` 学习输入数据要求；
- 从 `结果对比` 学习多情景评估；
- 从 `报告与导出` 学习交付件生成。
