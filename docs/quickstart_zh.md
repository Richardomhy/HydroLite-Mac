# HydroLite Studio 快速开始

适用版本：v0.5.0-alpha.2

## 1. 安装依赖

```bash
cd "/Users/minghenyu/Documents/hydrolite 模型"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 2. 检查版本和环境

```bash
python -m hydrolite version
python -m hydrolite healthcheck
```

## 3. 启动 HydroLite Studio

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

打开：

```text
http://localhost:8501
```

## 4. 载入 demo 项目

在侧边栏确认项目路径：

```text
projects/demo_project
```

如果项目不存在，先运行：

```bash
python -m hydrolite project create projects/demo_project
```

## 5. 推荐演示流程

```text
项目首页 -> 数据与校验 -> 情景运行 -> GEE 数据中心 -> SWMM 联动 -> OpenHydroNet AI 输入 -> 结果对比 -> 报告与导出
```

## 6. CLI 演示流程

```bash
python -m hydrolite project validate projects/demo_project
python -m hydrolite project run projects/demo_project demo_gee.yaml
python -m hydrolite project batch projects/demo_project
python -m hydrolite project compare projects/demo_project
python -m hydrolite project export projects/demo_project
```

## 7. 安全边界

- 不修改 `data_raw/` 原始数据；
- 不提交 Google credentials、token、API key；
- 不提交 `.streamlit/secrets.toml`；
- 不提交 external OpenHydroNet 仓库；
- 不提交模型权重、checkpoint 或训练数据大文件；
- OpenHydroNet 当前只生成 input package，不做真实 AI 预测。
