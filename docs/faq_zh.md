# HydroLite Studio FAQ

## HydroLite Studio 是 MIKE 的替代品吗？

不是。v0.5.0-alpha.2 是轻量级 MVP 和演示工作台，不是 MIKE 的完整替代。工程审查和正式设计仍需要专业软件、实测资料和人工复核。

## 会修改 data_raw 原始数据吗？

不会。`data_raw/` 被视为只读区域。SWMM 会先把原始 INP 复制到输出目录中的 `working.inp`，再写入联动边界。

## 为什么 Streamlit Cloud 上 SWMM 可能失败？

SWMM Python 后端依赖二进制包，云端环境可能不兼容。HydroLite 会优雅降级，保留主水文流程、已有结果展示和诊断信息。

## GEE 为什么显示 unavailable？

通常是缺少 `GEE_PROJECT`、未完成 Earth Engine 认证、Google Cloud 项目未启用 Earth Engine API，或当前账号没有权限。请本地完成认证，不要把凭证提交到仓库。

## OpenHydroNet 页面是否已经在做 AI 洪水预测？

没有。当前只生成 OpenHydroNet-ready input package，不训练模型，不运行真实大规模推理，也不提交外部仓库或模型权重。

## demo_observed_streamflow 是真实水文站数据吗？

不是。它是 synthetic/demo only 数据，用于演示模型评估和 OpenHydroNet 输入包结构。

## 参数建议可以直接用于工程设计吗？

不建议。GEE 参数建议是启发式结果，不是率定结果。工程使用前必须进行参数率定、敏感性分析和人工复核。

## 发布包里包含什么？

`release/` 包含 demo project zip、release manifest、安装说明、演示流程、限制说明和 release notes。不包含 credentials、external 仓库或模型权重。

## 最短演示命令是什么？

```bash
python -m hydrolite version
python -m hydrolite healthcheck
python -m streamlit run streamlit_app.py --server.headless true
```

然后访问 `http://localhost:8501`。
