# 成果资产管理

成果中心按项目、Run、类型和质量状态筛选文件，并支持 CSV/XLSX/JSON/YAML/Markdown/GeoJSON 和图片的轻量预览。

命令包括 `artifacts run`、`artifacts validate` 和 `artifacts bundle`。

大型 DSS、HDF5、NetCDF 只显示元数据。Bundle 排除 raw、external、数据库、凭证、模型权重和大型二进制。
