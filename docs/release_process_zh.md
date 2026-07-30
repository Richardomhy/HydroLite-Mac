# macOS 发布流程

1. 创建 `hydrolite-build` 并运行诊断。
2. 构建 PyInstaller onedir 后端和 Swift 壳。
3. 组装、资源审计和安全审计。
4. ad-hoc 本地验证；正式发布改用明确 Developer ID。
5. 生成并验证 ZIP/DMG、SHA256 和 release manifest。
6. Developer ID 门禁通过后，使用钥匙串 profile 显式公证、staple、复验。
7. 更新 Feed 必须使用 HTTPS、EdDSA 和 Apple 签名。

构建产物不提交 Git，不创建或移动 release tag。公证凭证、证书和私钥不进入项目。
