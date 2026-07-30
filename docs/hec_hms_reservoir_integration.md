# HEC-HMS Reservoir 集成

HydroLite 生成原创 Reservoir Outflow Curve 项目骨架并安全探测 Project.open。未验证 paired-data 引用或控制窗口时，compute 会标记 `skipped_gate_failed`，不会启动 HMS/Java；官方示例如需研究仅可复制到 `output/`，不纳入版本库。

4.13 官方 `river_bend` 参考用于核对 Reservoir 和 `.pdata` 表结构；本机参考项目 DSS 无法访问时，compute 门禁保持失败，绝不填充伪造的水位、库容、入流或出流结果。
