# 平台能力矩阵

| macOS desktop 0.7.0-dev | 状态 |
|---|---|
| SwiftUI/WKWebView arm64 壳 | local ad-hoc MVP |
| HydroLite/Streamlit onedir 后端 | partial |
| QGIS / HEC-HMS | optional external |
| Developer ID / 公证 | credentials_required |
| Sparkle 正式 Feed | configuration missing；手动 manifest fallback |

平台统一使用 available、partial、planned、blocked 和 unavailable_optional 状态。洪水预测在本版本由 planned 提升为 partial；干旱预测和 water_quality 保持 planned；HEC-HMS Reservoir 保持 blocked。

统一数据中心和外部连接器现为 `partial`：小型上传、字段映射、质量、血缘和输入准备可用；大型 GIS、NetCDF/HDF5 和真实平台下载依赖可选本地环境与显式确认。Water quality 仍为 `planned`，仅完成数据接口。

| Production operations | Status | Notes |
|---|---|---|
| Runtime database and project registry | partial | SQLite local runtime; no server dependency |
| Run/task orchestration and recovery | partial | FIFO, timeout, cancel, explicit retry |
| Artifact center and validation | partial | Lightweight preview; large scientific files metadata only |
| Local/cloud deployment gates | partial | Cloud blocks local QGIS/HEC-HMS and large downloads |

能力矩阵同时在 Streamlit 首页和 `output/flood_forecast/platform_capability_matrix.xlsx` 显示。partial 表示已有受限 MVP，不代表工程适用或业务验证完成。
