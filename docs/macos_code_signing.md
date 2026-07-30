# macOS 代码签名

发行等级：

1. `development_bundle`：已组装，未签名。
2. `local_ad_hoc_app`：本机 ad-hoc 签名，可用于开发验证。
3. `developer_id_signed`：需要有效 Developer ID Application 身份。
4. `notarized_distribution`：需要 Developer ID 和 notarytool profile。

```bash
python -m hydrolite desktop signing-status
python -m hydrolite desktop sign ad_hoc
HYDROLITE_CODESIGN_IDENTITY="Developer ID Application: ..." \
  python -m hydrolite desktop sign developer_id
```

签名顺序为嵌套 Mach-O、后端、Swift 主程序、最外层 App，不以 `--deep` 代替逐层签名。Developer ID 才启用 timestamp 与 hardened runtime。初始 entitlement 为空，不含 App Sandbox、JIT 或 `get-task-allow`。证书、Team ID 和密钥只通过本地环境/钥匙串提供。

Ad-hoc 构建通过 `codesign --verify`，但 `spctl` 拒绝是预期结果，不代表已获 Apple 信任。
