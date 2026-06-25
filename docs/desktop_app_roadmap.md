# Desktop App Roadmap

## 为什么暂时不重写桌面端

HydroLite Studio 当前的 Streamlit 本地版已经能覆盖项目管理、校验、运行、对比、报告和演示。重写桌面端会重复大量 UI 与状态逻辑，增加维护成本。

## 当前主入口

当前推荐入口仍是：

```bash
python -m streamlit run streamlit_app.py --server.headless true
```

本地版适合完整 GEE/SWMM/OpenHydroNet-ready 工作流；在线版适合演示和反馈。

## 技术路线对比

| 路线 | 优点 | 风险 | 建议 |
| --- | --- | --- | --- |
| 本地启动器 | 最小改动，一键打开 Streamlit | 仍依赖浏览器 | v0.7.0 优先 |
| PySide6 | Python 生态一致 | UI 重写成本高，打包重 | 仅评估 |
| Tauri | 包小，桌面体验好 | 需要 Rust/前端桥接 | 仅评估 |
| Electron | 生态成熟 | 包大，维护成本高 | 不优先 |

## macOS 打包风险

- Python、Streamlit、SWMM、GEE、QGIS 路径复杂。
- Apple Silicon 与 x86_64 依赖差异。
- 签名、公证和权限提示需要额外流程。
- 外部求解器不适合硬打包进主应用。

## 推荐路线

1. 保持 Streamlit 为唯一业务 UI。
2. 做一个最小本地启动器，只负责检查环境、启动服务、打开浏览器。
3. 桌面壳不复制模型计算代码。
4. 只有当用户反馈证明需要离线桌面体验时，再评估 PySide6/Tauri。
