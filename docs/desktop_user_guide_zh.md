# HydroLite Studio macOS 桌面版用户指南

侧栏“历史洪水验证”用于查看事件目录、QC、回放、同化、提前期和报告。桌面能力矩阵中的 Historical Flood Validation 与 Data Assimilation 均为 partial；本地版可运行有界批处理，云端主要查看预生成结果。

1. 从 DMG 将 App 拖入 Applications。
2. 从 Finder 启动，等待本地后端健康检查完成。
3. 使用项目中心创建/打开项目，在数据中心校验输入，在运行中心执行轻量任务。
4. 从菜单打开数据目录、日志或检查更新。
5. 使用 `HydroLite Studio > Quit` 正常退出。

用户数据位于 `~/Library/Application Support/HydroLite Studio/`，日志位于 `~/Library/Logs/HydroLite Studio/`。QGIS、HEC-HMS、GEE 与外部连接器为可选能力，不随 App 内置。0.7.0-dev 为开发通道，ad-hoc 包仅供本机验证。
