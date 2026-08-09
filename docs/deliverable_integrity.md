# Deliverable Integrity

HydroLite 不通过 `chmod` 假装冻结成果。批准时，Deliverable Manifest 固定 artifact IDs、artifact versions 和 SHA-256；后续文件内容变化会使验证失败，旧 checksum 不会被自动覆盖。

完整性接口包括 `hash_file`、`hash_manifest`、`verify_artifact`、`verify_report`、`verify_deliverable` 和 `verify_project_package`。

正式 artifact 不允许原路径静默覆盖。重新生成时应写入新路径并创建新 artifact version，记录 `supersedes_artifact_id`。批准后所有引用成果标记 `frozen`。

Manifest 和报告交付元数据使用项目相对、工作区相对或 `external-reference/<name>` 路径，不暴露用户 Home 绝对路径。

```bash
python -m hydrolite delivery verify <deliverable_id>
python -m hydrolite project verify-package <package>
```

交付包敏感扫描只报告 file、rule、status，不输出检测到的 secret 内容。
