# macOS 构建环境

执行：

```bash
bash scripts/create_macos_build_env.sh
conda run -n hydrolite-build python -m hydrolite desktop build
```

脚本创建或复用 Python 3.12 的 `hydrolite-build`，不修改 Conda base，不使用 `sudo`。环境、锁定依赖和诊断写入 `output/macos_packaging/`，本地绝对路径和凭证不进入锁文件。

PyInstaller 使用 onedir，便于排查资源、逐层签名和增量验证。桌面核心不默认捆绑 torch、TensorFlow、QGIS、HEC-HMS、重型 GIS 库或模型权重。
