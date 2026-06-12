# OpenHydroNet AI 洪水预测插件骨架

## 目标

OpenHydroNet AI 洪水预测板块用于未来接入基于 Google Research flood-forecasting 思路的河流洪水预测工作流。当前阶段只提供配置、适配器、外部仓库检测、隔离环境诊断、smoke test 和 Streamlit 入口。

## 与 Google Flood Hub 的关系

OpenHydroNet 的背景来自 google-research/flood-forecasting，与 Flood Hub 相关研究方向有关。本项目中的 OpenHydroNet 板块不是官方 Google 产品，也不代表 Google Flood Hub 服务，只是 HydroLite-Mac 的未来扩展接口。

## 依赖

未来真实推理通常需要 PyTorch 及相关科学计算依赖。当前阶段建议使用隔离 conda 环境 `hydrolite-openhydronet`，不要把 AI 依赖安装进 HydroLite 主环境。

## 外部仓库接入方式

OpenHydroNet 相关源码不复制进本仓库提交。建议使用：

```bash
bash scripts/openhydronet_env/clone_openhydronet_repo.sh
```

默认目标目录：

```text
external/openhydronet/flood-forecasting
```

`external/` 已被 `.gitignore` 忽略，因此外部大仓库不会进入 HydroLite-Mac 的 git 提交。

也可以使用环境变量指向项目外部仓库：

```bash
export OPENHYDRONET_HOME="/path/to/flood-forecasting"
```

## 隔离环境

创建隔离环境：

```bash
bash scripts/openhydronet_env/create_openhydronet_env.sh
```

脚本会优先创建 `hydrolite-openhydronet` conda 环境，Python 3.11 不兼容时尝试 Python 3.10，并安装 `torch`、`numpy`、`pandas`、`pyyaml` 等基础依赖。如果外部仓库存在 `requirements.txt`，脚本会尝试在隔离环境中安装。

## Apple Silicon / MPS 注意事项

Apple Silicon Mac 上 PyTorch 可能使用 MPS 加速，但第三方研究代码未必完全支持 MPS。当前 smoke test 只检测 MPS/CUDA/CPU 状态，不训练模型、不运行真实推理。

## Smoke Test 阶段

运行：

```bash
python -m hydrolite openhydronet diagnose
python -m hydrolite openhydronet smoke configs/openhydronet.example.yaml
```

输出：

```text
output/openhydronet/smoke_test_summary.xlsx
output/openhydronet/smoke_test_report.md
```

smoke test 只检查配置、外部仓库路径、README/requirements、torch 和加速器状态，不下载大数据、不训练模型、不运行真实洪水预测。

## 输入数据需求

未来可能需要：

- 流域静态属性。
- 气象强迫数据。
- 观测流量。
- GEE 生成的地形、土地利用、水体和降雨特征。
- HydroLite/SWMM 生成的情景模拟结果。

真实推理阶段还需要明确的数据清单包括：流域边界、流域静态属性、时间对齐的气象强迫、观测流量、预测时段、模型 checkpoint、归一化参数、训练/验证数据版本和结果评估基准。

## 与 HydroLite、GEE、SWMM 的关系

- HydroLite：提供水文模拟过程和情景管理。
- GEE：提供遥感和地理空间输入。
- SWMM：提供城市排水管网模拟结果。
- OpenHydroNet：未来用于 AI 洪水预测和多源结果对比。

## 阶段开发路线

1. 插件骨架和诊断脚本。
2. 隔离环境和 smoke test。
3. GEE 输入特征接入。
4. 本地流域 schema 适配。
5. 与 HydroLite/SWMM 情景结果进行联合对比。
