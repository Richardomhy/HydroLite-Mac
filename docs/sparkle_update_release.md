# Sparkle RC 更新

App 内置 Sparkle 2.9.4 和 HTTPS Feed，但只有注入 `SUPublicEDKey` 且安全密钥可用时才能签名更新包。M7B2 生成 `output/desktop_release/update_staging/appcast.xml`，不上传或覆盖生产 Feed。

缺少密钥时状态为 `blocked_signing_key_missing`，损坏包或无效签名必须被拒绝。
