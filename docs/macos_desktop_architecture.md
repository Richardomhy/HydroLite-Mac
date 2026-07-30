# macOS 桌面架构

HydroLite Studio 0.7.0-dev 使用两层结构：SwiftUI/WKWebView 原生壳启动 PyInstaller onedir 后端；后端只监听动态 `127.0.0.1` 端口并运行现有 Streamlit 应用。两层仅通过 loopback URL、PID、port 和健康 manifest 通信，不提供任意 shell 桥。

应用数据、日志和缓存分别写入 `~/Library/Application Support/HydroLite Studio/`、`~/Library/Logs/HydroLite Studio/` 和 `~/Library/Caches/HydroLite Studio/`。Bundle 只读，不写 SQLite、上传或结果。

QGIS 与 HEC-HMS 体积大且有独立授权/运行时，因此只做本机探测，不随 App 打包。当前仅验证 Apple Silicon arm64 和 macOS 13 及以上；Universal 2 后续处理。
