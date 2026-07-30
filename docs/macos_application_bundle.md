# macOS App Bundle

```bash
python -m hydrolite desktop build-backend
python -m hydrolite desktop build-shell
python -m hydrolite desktop assemble
python -m hydrolite desktop resources
```

目标为 `dist/macos/HydroLite-Studio-0.7.0-arm64.app`，Bundle ID 为 `com.hydrolite.studio`，短版本为 `0.7.0`，应用内版本为 `0.7.0-dev`。构建号取 `HYDROLITE_BUILD_NUMBER` 或 Git commit count。

Bundle 不包含 `data_raw`、`output`、runtime DB、日志、用户上传、DSS/HDF5/NetCDF、凭证、模型权重、测试、`.git`、QGIS 或 HEC-HMS。可修改模板会先复制到用户数据目录。
