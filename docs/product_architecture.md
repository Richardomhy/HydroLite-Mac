# HydroLite Studio 产品架构

## M7B1 交付治理

项目产品层新增独立交付生命周期：Working Project -> Project Version -> Data/Configuration Snapshot -> Versioned Run -> Artifacts -> Technical Review -> Approval -> Frozen Deliverable -> Integrity Verification -> Delivery/Portable Package。

该治理层复用 Runtime DB、Run Manager、Artifact Store、环境快照和 provenance，不建立第二套运行数据库，不改变科学算法或 HydroLite 水量账本。详见 [Project Versioning](project_versioning.md)、[Delivery Review](delivery_review_workflow.md)、[Integrity](deliverable_integrity.md)、[Package Format](project_package_format.md) 和 [Scientific vs Delivery Status](scientific_vs_delivery_status.md)。

M7A 将既有模型、数据平台和运行平台组织为场景驱动的产品界面，不新增科学算法，也不改变模型数学实现。

顶层信息架构为：**首页、项目、场景、数据、运行、成果、方法实验室、系统**。普通用户从“要解决什么问题”进入，而不是先选择模型。标准流程为：创建或打开项目 → 选择场景 → 查看数据需求 → 数据就绪度检查 → 配置 → 审阅 → 提交现有 Run Manager → 查看可信度和成果。

Scenario 是业务入口，Workflow 是执行逻辑。`hydrolite/scenario_registry.py` 只映射现有 Recipe，不复制 Workflow。`hydrolite/product_status.py` 汇总 Capability、Model、Research 和环境证据，禁止把 `synthetic_demo` 或 `framework_ready` 自动升级为真实数据验证。结果解释器只整理已提供指标，不生成不存在的科学结论。

M7A 不包含新模型、训练、GEE 下载器、用户账号服务、桌面打包、签名、公证或 M7B 审批工作流。
