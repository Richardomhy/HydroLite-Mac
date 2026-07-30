# macOS 安全更新

当前状态为 `framework_ready_configuration_missing`：原生壳有检查更新入口和 HTTPS release manifest 手动 fallback，但尚未嵌入 Sparkle 2，也没有正式 Feed。

配置正式更新时必须同时满足：HTTPS appcast、Sparkle EdDSA 签名、Apple Code Signing、版本递增、相同 Bundle ID，以及 Developer ID 模式下相同 Team ID。EdDSA 私钥保存在开发者钥匙串，绝不进入仓库。

未配置 Feed 时应用只提示“更新源尚未配置”，不会访问虚构 URL，也不会自行替换 App。未签名更新不得静默安装。
