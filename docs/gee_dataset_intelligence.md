# GEE 数据集智能目录

HydroLite 使用自有、离线优先的元数据目录；官方来源记录为 `gs://earthengine-stac/catalog.json`。未认证时仍可检索、比较、推荐和生成代码片段，但任何实际 GEE 计算或导出必须标记 `authentication_required`。

本目录是 HydroLite 的 clean-room 元数据工具，只使用官方 STAC 根目录与官方数据集页面；不复用第三方 Skill 的代码、目录资产或文案。检索先应用硬过滤；没有完全匹配时返回 `no_exact_match`，并显式说明任何放宽条件。bbox 仅为目录外包络检查，实际使用仍需 `runtime_footprint_check_required`。

目录 refresh 默认为 dry-run；execute 仅以小型元数据 fixture 原子更新本地缓存，不镜像 Google HTML。第三方 `gee-dataset-intelligence-skill` 许可证状态为 `license_file_missing`，未被复制、下载、作为依赖或打包。
