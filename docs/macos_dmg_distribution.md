# macOS DMG 与 ZIP

```bash
python -m hydrolite desktop package-zip
python -m hydrolite desktop package-dmg
bash scripts/verify_macos_package.sh
```

DMG 仅包含 App、`Applications` 快捷方式和安装说明。把 App 拖入 Applications 后启动；开发版为 ad-hoc 签名，Gatekeeper 可能阻止，正式公开分发应使用 Developer ID 和公证版本。`dist/macos/SHA256SUMS` 用于完整性核对。

回滚时退出 App，保留用户数据目录，将 Applications 中 App 替换为上一版本。不要用新版本覆盖正在运行的 App。
