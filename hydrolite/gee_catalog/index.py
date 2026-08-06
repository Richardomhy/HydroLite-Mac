from __future__ import annotations

from hydrolite.gee_catalog.loader import load_catalog


def build_index(records=None) -> dict[str, dict]:
    return {row["asset_id"].lower(): row for row in (records or load_catalog())}
