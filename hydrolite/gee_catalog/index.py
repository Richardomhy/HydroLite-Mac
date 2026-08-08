from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def build_catalog_index(records: Iterable[dict]) -> pd.DataFrame:
    rows = []
    for row in records:
        rows.append({
            "asset_id": row.get("asset_id"), "title": row.get("title"), "provider": row.get("provider"),
            "dataset_type": row.get("dataset_type"), "categories": " ".join(row.get("categories", [])),
            "use_cases": " ".join(row.get("hydrolite_use_cases", [])), "bands": " ".join(str(item.get("name", "")) if isinstance(item, dict) else str(item) for item in row.get("bands", [])),
            "keywords": " ".join(row.get("keywords", [])), "nominal_scale_m": row.get("nominal_scale_m"), "status": row.get("status"),
        })
    return pd.DataFrame(rows)


def write_catalog_index(index: pd.DataFrame, path: str | Path) -> Path:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True); index.to_parquet(target, index=False); return target


def load_catalog_index(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def build_text_index(records: Iterable[dict]) -> dict[str, list[str]]:
    return {str(row.get("asset_id")): str(row).lower().split() for row in records}


def _term_index(records: Iterable[dict], key: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in records:
        values = row.get(key, [])
        if not isinstance(values, list): values = [values]
        for value in values:
            value = value.get("name") if isinstance(value, dict) else value
            if value: result.setdefault(str(value).lower(), []).append(str(row.get("asset_id")))
    return result


def build_band_index(records: Iterable[dict]) -> dict[str, list[str]]: return _term_index(records, "bands")
def build_provider_index(records: Iterable[dict]) -> dict[str, list[str]]: return _term_index(records, "provider")
def build_category_index(records: Iterable[dict]) -> dict[str, list[str]]: return _term_index(records, "categories")
def build_use_case_index(records: Iterable[dict]) -> dict[str, list[str]]: return _term_index(records, "hydrolite_use_cases")


def validate_catalog_index(index: pd.DataFrame) -> list[str]:
    return [] if "asset_id" in index.columns and index["asset_id"].notna().all() else ["index_missing_asset_id"]
