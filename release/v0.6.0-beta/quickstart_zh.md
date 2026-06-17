# HydroLite Studio 快速开始

适用版本：v0.5.0-alpha.2

## 1. 在线体验入口

无需本地安装，可直接打开：

```text
https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app
```

在线版适合快速演示、查看示例项目、浏览结果表格和报告。由于云端环境限制，GEE 认证、SWMM 二进制后端、OpenHydroNet 外部仓库等完整工作流建议在本地运行。

GitHub 仓库：

```text
https://github.com/Richardomhy/HydroLite-Mac.git
```

第一次使用推荐打开 Streamlit 后先进入左侧导航的 **教程与 Demo** 页面，按照引导完成一次完整软件演示。

真实项目建议先进入 **数据模板** 页面下载 `templates/data` 标准模板，整理数据后再使用项目向导创建项目。

## 2. 本地完整运行入口

本地版适合完整 GEE/SWMM/OpenHydroNet 工作流、隔离 SWMM 求解器、GEE 认证和项目导出。

## 3. 安装依赖

```bash
cd "<PROJECT_ROOT>"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 4. 检查版本和环境

```bash
python -m hydrolite version
python -m hydrolite healthcheck
```

## 5. 启动 HydroLite Studio

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

打开：

```text
http://localhost:8501
```

## 6. 载入 demo 项目

在侧边栏确认项目路径：

```text
projects/demo_project
```

如果项目不存在，先运行：

```bash
python -m hydrolite project create projects/demo_project
```

## 7. 在线版与本地版区别

- 在线版：适合演示 UI、查看 demo 输出、阅读报告和熟悉工作流；
- 本地版：适合运行完整模型、配置 GEE、使用 SWMM 隔离求解器、准备 OpenHydroNet 外部仓库；
- 两者都不应提交 secrets、credentials、external 仓库或模型权重。

## 8. 推荐演示流程

```text
教程与 Demo -> 项目首页 -> 数据与校验 -> 情景运行 -> GEE 数据中心 -> SWMM 联动 -> OpenHydroNet AI 输入 -> 结果对比 -> 报告与导出
```

也可以使用 CLI 查看教程清单：

```bash
python -m hydrolite tutorial list
python -m hydrolite tutorial checklist projects/demo_project
```

下载和校验真实项目数据模板：

```bash
python -m hydrolite templates export-all templates_export/
python -m hydrolite templates validate templates/data/examples/
```

## 9. CLI 演示流程

```bash
python -m hydrolite project validate projects/demo_project
python -m hydrolite project run projects/demo_project demo_gee.yaml
python -m hydrolite project batch projects/demo_project
python -m hydrolite project compare projects/demo_project
python -m hydrolite project export projects/demo_project
```

## 10. 安全边界

- 不修改 `data_raw/` 原始数据；
- 不提交 Google credentials、token、API key；
- 不提交 `.streamlit/secrets.toml`；
- 不提交 external OpenHydroNet 仓库；
- 不提交模型权重、checkpoint 或训练数据大文件；
- OpenHydroNet 当前只生成 input package，不做真实 AI 预测。
