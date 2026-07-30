# 本地部署

## macOS 桌面版

0.7.0-dev 使用独立 `hydrolite-build` 环境构建 arm64 SwiftUI/WKWebView App，后端只监听动态 `127.0.0.1` 端口；QGIS 和 HEC-HMS 保持外部探测。参见 [构建环境](macos_build_environment.md) 和 [桌面用户指南](desktop_user_guide_zh.md)。

启动：

```bash
bash scripts/launch_hydrolite_local.sh
```

访问 `http://127.0.0.1:8501`。PID 和日志位于 `~/.hydrolite/runtime/`。

停止：

```bash
bash scripts/stop_hydrolite_local.sh
```

停止脚本验证 PID 对应 HydroLite Streamlit，不按名称批量终止 Python。
