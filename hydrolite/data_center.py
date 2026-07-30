from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import zipfile

import pandas as pd


FORBIDDEN = ("data_raw", "external", "raw/", "credential", "secret", ".dss", ".h5", ".hdf5", ".nc", ".pt", ".pth", ".ckpt", ".onnx")
SAFE_REPORT_PREFIXES = (
    "data_type_registry", "supported_formats", "connector_status", "project_data_requirements",
    "model_data_readiness", "missing_data_actions", "data_quality_summary", "lineage_summary",
    "input_build_summary", "data_center_report", "data_center_manifest",
)


def write_data_center_reports(output_dir: str | Path, workspace_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir).resolve()
    workspace = Path(workspace_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "status": "partial",
        "workspace_name": workspace.name,
        "workspace_manifest": "workspace_manifest.json",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_files_included": False,
        "credentials_included": False,
        "limitations": ["Heavy GIS, NetCDF, HDF5 and platform downloads require optional local dependencies.", "External downloads require explicit execution."],
    }
    manifest_path = output / "data_center_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    zh = output / "data_center_report_zh.md"
    en = output / "data_center_report_en.md"
    zh.write_text(f"# 统一数据中心报告\n\n- 状态：`partial`\n- 工作区：`{workspace.name}`\n- 原始上传保持只读：`True`\n- 外部下载：`未自动执行`\n", encoding="utf-8")
    en.write_text(f"# Unified Data Center Report\n\n- Status: `partial`\n- Workspace: `{workspace.name}`\n- Raw uploads immutable: `True`\n- External downloads: `not automatically executed`\n", encoding="utf-8")
    bundle = output / "data_center_bundle.zip"
    allowed_suffixes = {".md", ".json", ".xlsx", ".csv", ".yaml", ".yml", ".geojson"}
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in output.rglob("*"):
            if not path.is_file() or path == bundle or path.suffix.lower() not in allowed_suffixes or not path.name.startswith(SAFE_REPORT_PREFIXES):
                continue
            name = path.relative_to(output).as_posix()
            if not any(token in name.lower() for token in FORBIDDEN):
                archive.write(path, name)
        for folder in ("mappings", "quality", "lineage"):
            source = workspace / folder
            for path in source.rglob("*") if source.is_dir() else []:
                if path.is_file() and path.suffix.lower() in allowed_suffixes:
                    archive.write(path, f"workspace/{folder}/{path.relative_to(source).as_posix()}")
    return {"zh": zh, "en": en, "manifest": manifest_path, "bundle": bundle}


def validate_data_center_bundle(bundle_path: str | Path) -> dict:
    with zipfile.ZipFile(bundle_path) as archive:
        names = archive.namelist()
    blocked = [name for name in names if name.startswith("/") or any(token in name.lower() for token in FORBIDDEN)]
    return {"status": "passed" if not blocked else "failed", "blocked": blocked, "file_count": len(names)}
