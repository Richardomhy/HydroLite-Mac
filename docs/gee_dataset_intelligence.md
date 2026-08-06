# GEE 数据集智能目录

HydroLite 使用自有、离线优先的元数据目录；官方来源记录为 `gs://earthengine-stac/catalog.json`。未认证时仍可检索、比较、推荐和生成代码片段，但任何实际 GEE 计算或导出必须标记 `authentication_required`。

目录 refresh 默认为 dry-run；execute 仅以小型元数据 fixture 原子更新本地缓存，不镜像 Google HTML。第三方 `gee-dataset-intelligence-skill` 许可证状态为 `license_file_missing`，未被复制、下载、作为依赖或打包。
