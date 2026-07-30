# macOS 安全更新

当前状态为 `framework_integrated_signing_key_missing`：原生壳已通过 SwiftPM 集成 Sparkle 2.9.4，Feed 指向 GitHub Release 的 HTTPS `appcast.xml`。正式更新仍需要打包时通过 `HYDROLITE_SPARKLE_PUBLIC_KEY` 注入 EdDSA 公钥。

配置正式更新时必须同时满足：HTTPS appcast、Sparkle EdDSA 签名、Apple Code Signing、版本递增、相同 Bundle ID，以及 Developer ID 模式下相同 Team ID。EdDSA 私钥保存在开发者钥匙串，绝不进入仓库。

未注入公钥时应用只提示“更新签名尚未配置”，不会安装更新。Sparkle 私钥只保存在开发者钥匙串，证书、公证凭证和私钥均不得写入仓库或发行包。
