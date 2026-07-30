# macOS 公证

本项目只使用 `xcrun notarytool`。默认命令是 dry-run：

```bash
python -m hydrolite desktop notarization-gate
python -m hydrolite desktop notarize dry-run
```

无 Developer ID 或 `HYDROLITE_NOTARY_PROFILE` 时状态为 `credentials_required`。实际上传必须先通过 hardened runtime、嵌套签名、包验证和安全审计，再显式执行：

```bash
HYDROLITE_NOTARY_PROFILE=hydrolite-notary \
  python -m hydrolite desktop notarize execute
```

凭证只保存在钥匙串 profile，脚本不接收或打印明文密码。接受后还需 staple、验证 staple 并重新运行 `spctl`；仅 return code 0 不视为完成。
