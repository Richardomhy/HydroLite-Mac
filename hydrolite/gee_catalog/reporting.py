from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from hydrolite.gee_catalog.loader import load_catalog_records
from hydrolite.gee_catalog.status import catalog_status
from hydrolite.gee_catalog.validation import validate_catalog


def build_catalog_statistics(records: list[dict]) -> dict:
    return {"record_count": len(records), "providers": pd.Series([row.get("provider") for row in records]).value_counts(dropna=False).to_dict(), "dataset_types": pd.Series([row.get("dataset_type") for row in records]).value_counts(dropna=False).to_dict(), "deprecated_count": sum(bool(row.get("deprecated")) for row in records)}


def build_catalog_change_report(old: list[dict], new: list[dict]) -> list[dict]:
    old_ids, new_ids = {row["asset_id"] for row in old}, {row["asset_id"] for row in new}
    return [{"change": "added", "asset_id": value} for value in sorted(new_ids - old_ids)] + [{"change": "removed", "asset_id": value} for value in sorted(old_ids - new_ids)]


def build_catalog_validation_report(result: dict) -> str:
    return f"# GEE catalog validation\n\nStatus: `{result['status']}`\n\nRecords: {result['record_count']}\n"


def write_catalog_report(output_dir: str | Path = "output/gee_catalog_intelligence", result: dict | None = None) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True); records = load_catalog_records(); validation = result or validate_catalog(); status = catalog_status(); stats = build_catalog_statistics(records)
    paths = {"status": output / "catalog_status.json", "statistics": output / "catalog_statistics.xlsx", "validation": output / "catalog_validation.json", "changes": output / "catalog_change_report.xlsx", "rejected": output / "rejected_records.xlsx", "report_zh": output / "gee_catalog_report_zh.md", "report_en": output / "gee_catalog_report_en.md", "manifest": output / "gee_catalog_manifest.json", "refresh_zh": output / "refresh_report_zh.md", "refresh_en": output / "refresh_report_en.md"}
    public_status = {key: value for key, value in status.items() if key not in {"catalog_root", "records_path", "manifest_path", "fixture_path"}}
    paths["status"].write_text(json.dumps(public_status, ensure_ascii=False, indent=2), encoding="utf-8"); paths["validation"].write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"); paths["manifest"].write_text(json.dumps({"status": public_status, "record_count": len(records), "fixture_only": status["status"] == "fixture_only"}, ensure_ascii=False, indent=2), encoding="utf-8")
    with pd.ExcelWriter(paths["statistics"]) as writer: pd.DataFrame([stats]).to_excel(writer, index=False, sheet_name="summary")
    pd.DataFrame(build_catalog_change_report([], records)).to_excel(paths["changes"], index=False); pd.DataFrame(validation.get("errors", {}).items(), columns=["check", "detail"]).to_excel(paths["rejected"], index=False)
    body_en = f"# HydroLite GEE Catalog\n\nStatus: `{status['status']}`. Offline metadata remains usable; GEE compute requires authentication.\n\nRecords: {len(records)}. This is a curated fixture when no local official refresh exists.\n"
    body_zh = f"# HydroLite GEE 数据集目录\n\n状态：`{status['status']}`。离线元数据可继续查询；实际 GEE 计算需要本地认证。\n\n记录数：{len(records)}。在未完成本地官方刷新时，这是精选的离线元数据 fixture，而非完整镜像。\n"
    paths["report_zh"].write_text(body_zh, encoding="utf-8"); paths["refresh_zh"].write_text(body_zh, encoding="utf-8")
    paths["report_en"].write_text(body_en, encoding="utf-8"); paths["refresh_en"].write_text(body_en, encoding="utf-8")
    return paths
