# Local Smoke Test

用于在本地验证 HydroLite Studio v0.6.0-beta 基本可运行。

## 1. Clone 仓库

```bash
git clone https://github.com/Richardomhy/HydroLite-Mac.git
cd HydroLite-Mac
```

## 2. 创建环境

推荐 Python 3.11：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果使用 conda：

```bash
conda create -n hydrolite python=3.11 -y
conda activate hydrolite
python -m pip install -r requirements.txt
```

## 3. 启动 Streamlit

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

浏览器访问：

- <http://localhost:8501>
- <http://127.0.0.1:8501>

## 4. 运行 Healthcheck

```bash
python -m hydrolite version
python -m hydrolite healthcheck
python -m hydrolite beta smoke-local
```

`healthcheck` 可能对可选后端给出 warning，例如 GEE/SWMM/OpenHydroNet 未配置；只要主流程和页面可用，仍可继续演示。

## 5. 运行 demo_project

```bash
python -m hydrolite project validate projects/demo_project
python -m hydrolite project batch projects/demo_project
python -m hydrolite project compare projects/demo_project
```

## 6. 导出报告

```bash
python -m hydrolite report project projects/demo_project
```

报告输出在：

```text
projects/demo_project/reports/
```

## 常见问题

- SWMM 后端失败：检查 `HYDROLITE_SWMM_PYTHON` 或使用项目内隔离环境脚本。
- GEE 不可用：确认 Google Earth Engine API、账号权限和 `GEE_PROJECT`。
- OpenHydroNet 不可用：确认外部仓库未被提交到 git，且只在本地配置。
- 端口占用：换用 `--server.port 8502`。

不要把 credentials、tokens、service account json、训练数据或模型权重提交到仓库。
