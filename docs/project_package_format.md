# HydroLite Project Package Format

Package schema version：`1`。支持 `thin` 和 `portable`。

## Thin

只包含项目、版本、数据引用、配置、Run/Artifact 元数据和 manifests，不复制输入数据。

## Portable

在 thin 内容上增加用户明确选择的小型必要数据和成果。不会默认包含整个项目，更不会包含 `data_raw`。

```text
project.json
package_manifest.json
versions/
data/
configs/
runs/
artifacts/
manifests/
```

`package_manifest.json` 保存 schema、project ID、mode、version IDs 和每个成员的 SHA-256。所有路径使用 ZIP 相对路径。

导入顺序固定为 Verify -> Preview -> Conflict Check -> Import。导入前阻断 zip-slip、绝对路径、symlink escape、重复 ID、checksum 错误、未支持 schema、secret、runtime DB、DSS/HDF5、模型权重和 `external`。若 project ID 已存在，默认 `import_as_copy`；也可 `block_with_conflict`，绝不静默覆盖。

```bash
python -m hydrolite project export <project> --mode thin
python -m hydrolite project verify-package <package>
python -m hydrolite project import <package> <target_root>
```
