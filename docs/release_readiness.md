# Desktop Release Readiness

RC 状态分别记录 Build、Signing、Notarization、Gatekeeper、Update 和 Distribution。`internal_rc_ready` 只证明本地构建与回归通过，不等于可公开分发。

`distribution_rc_ready` 必须同时通过 Developer ID、hardened runtime、timestamp、Apple notarization、stapling、Gatekeeper、安装回归和安全扫描。Sparkle 密钥状态单独决定 `secure_auto_update_ready`。
