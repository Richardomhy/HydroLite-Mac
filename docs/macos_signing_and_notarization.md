# macOS 签名与公证

Developer ID 通过 `HYDROLITE_CODESIGN_IDENTITY` 显式选择；多身份时不自动猜测。签名顺序为嵌套 Mach-O、Framework/XPC/Plug-in、主 App，不使用 `codesign --deep` 执行签名。

公证只在 Developer ID、hardened runtime、timestamp 和 `HYDROLITE_NOTARY_PROFILE` 均通过时用 `notarytool` 执行。凭证只存钥匙串，不进入仓库或命令行。
