# 方法借鉴实验室架构基线（M0）

## 边界

HydroLite 的方法实验室只独立实现公开资料中的通用思想。它不复制第三方仓库、论文正文、图表、数据资产或模型配置；也不将实验层替代 HydroLite 的水量账本。

`data_raw/` 与 `tmp_emergency_0722/` 为保护路径，不能作为实验输出或被实验步骤修改。实验产物只允许写入 `output/gee_catalog_intelligence/`、`output/research_methods/`、`output/method_inspiration/` 或 `output/flood_susceptibility/`。

## 共用接口

- `hydrolite.research_status`：后续能力使用统一的实验状态与方法准入状态。
- `hydrolite.provenance`：检查保护路径、解析允许的输出目录，并创建不含第三方资产的 provenance 记录。
- `config/research_sources.yaml`：机器可读的 clean-room 规则。当前第三方 GEE Skill 的许可证状态为 `license_file_missing`，只能采用 `method_inspired_clean_room`，不得复制或作为运行时依赖。

所有报告应显示："本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，不构成原论文模型的精确复现。"

## 现有扩展点

`model_registry.py` 用于实验模型登记，`capability_registry.py` 用于平台能力状态，`workflow_engine.py` 用于阶段和 recipe。CLI 已有 `research`、`gee-catalog`、`method` 与 `susceptibility` 命名空间。现有 `GeeConnector` 仅支持依赖/认证诊断和元数据计划；精选目录与真实 GEE 计算必须保持分离。

## 状态约束

本基线不升级能力：`water_quality` 保持 `planned`，`flood_forecast` 与 `drought_forecast` 保持 `partial`。后续图时序订正只能并列输出物理预测、订正项和订正后预测；双向时间模型只允许历史分析。

## M0 验收

测试必须验证保护路径、禁止资产、状态边界和 clean-room 规则；M0 不实现 GEE 目录、Gamma、河网图、水质或易发性算法。
