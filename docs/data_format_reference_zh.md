# 数据格式参考

| 类别 | 支持格式 | 关键要求 |
|---|---|---|
| 表格/时序 | CSV、TSV、XLSX、JSON | XLSX 需选择工作表和标题行；时间需可解析 |
| 矢量 | GeoJSON、ZIP Shapefile、GPKG、KML/KMZ、坐标 CSV | Shapefile 需 `.shp/.shx/.dbf/.prj`；KML/KMZ 按 WGS84 |
| 栅格 | GeoTIFF、ASCII Grid、NetCDF、HDF5 | 校验 CRS、分辨率、nodata 和范围；高级格式可能需可选依赖 |
| 模型 | YAML、HEC-HMS 文件、SWMM INP | DSS 只做本地引用诊断，不进入上传包 |

字段、单位和示例见 `templates/data_upload/`。降雨必须区分累计量、时段增量和强度。未知 CRS 或单位必须人工确认。
