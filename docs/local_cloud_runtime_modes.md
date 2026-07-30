# 本地与云端运行模式

- `local_full`：按门禁使用本地 QGIS、HEC-HMS、SWMM 和连接器。
- `local_light`：只运行轻量 HydroLite、校验和报告。
- `cloud_streamlit`：禁止本地 QGIS、HEC-HMS、大型下载和 ML 训练。
- `test`：使用隔离 runtime 验证轻量任务。
- `read_only`：只查看项目、Run 和成果。

云端不可用能力显示 blocked，不会调用用户 Mac。
