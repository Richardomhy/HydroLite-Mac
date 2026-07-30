# macOS 桌面故障排查

```bash
python -m hydrolite desktop diagnose
python -m hydrolite desktop resources
python -m hydrolite desktop security-audit
python -m hydrolite desktop signing-status
```

日志位于 `~/Library/Logs/HydroLite Studio/`。启动卡住时先确认没有旧的 `desktop_instance.lock`、后端端口仅为 `127.0.0.1`，并查看 `backend.stderr.log`。不要通过关闭 CORS/XSRF 或监听 `0.0.0.0` 规避问题。

Gatekeeper 拒绝 ad-hoc 构建是正常现象；公开分发需要 Developer ID 与公证。QGIS/HEC-HMS 未探测到只会禁用相应外部能力，HydroLite 独立工作流仍可使用。
