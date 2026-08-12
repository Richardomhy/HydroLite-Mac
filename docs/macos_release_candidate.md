# macOS Release Candidate

M7B2 使用 `python -m hydrolite desktop rc-build` 在 `dist/macos/rc/` 构建 arm64 RC1，不覆盖历史产物。构建只复用现有 PyInstaller backend、SwiftUI/WKWebView shell 和 Sparkle 2.9.4。

源码环境没有 Developer ID、notary profile 或 Sparkle 签名密钥时，结果严格标记为 `distribution_blocked_credentials`；不伪造签名、公证或 Gatekeeper 成功。
