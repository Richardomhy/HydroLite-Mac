# HydroLite Studio v0.7.0 Milestones

## M1：GIS/QGIS 可行性诊断

- 目标：确认 macOS 上 QGIS-LTR、QGIS.app、`qgis_process`、PyQGIS 的可用性。
- 产出：诊断命令、环境报告、QGIS Bridge 最小方案。
- 验收：无 QGIS 时优雅提示；有 QGIS 时能读取版本、路径和基础图层信息。

## M2：Excel/CSV 导入增强

- 目标：降低真实项目数据接入门槛。
- 产出：Excel 导入、批量 CSV 检查、字段映射、单位转换、行列级错误定位。
- 验收：模板数据可通过；错误数据能定位 sheet/行/列/字段。

## M3：轻量参数率定

- 目标：基于已有观测流量评估做小范围参数扫描。
- 产出：CN、lag_time、Muskingum K/X 扰动；NSE/RMSE/KGE 对比；率定报告。
- 验收：不做复杂优化；小样例可在短时间内完成。

## M4：报告模板增强

- 目标：提升报告交付质量。
- 产出：Word 样式模板、中文工程报告模板、封面、目录、表号、图题和免责声明。
- 验收：demo_project 可生成结构清晰的中文报告。

## M5：桌面版技术验证

- 目标：判断是否需要桌面壳，而不是重写业务。
- 产出：PySide6 / Tauri / Electron / 本地启动器对比和最小启动器原型。
- 验收：一键启动 Streamlit；不复制模型逻辑。

## M6：v0.7.0-beta 发布

- 目标：冻结 v0.7.0-beta。
- 产出：release notes、manifest、smoke test、GitHub Issues/Milestones 整理。
- 验收：不移动旧 tag；release 包不含 secrets、external、weights、data_raw。
