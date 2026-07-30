# 本地部署

启动：

```bash
bash scripts/launch_hydrolite_local.sh
```

访问 `http://127.0.0.1:8501`。PID 和日志位于 `~/.hydrolite/runtime/`。

停止：

```bash
bash scripts/stop_hydrolite_local.sh
```

停止脚本验证 PID 对应 HydroLite Streamlit，不按名称批量终止 Python。
