from __future__ import annotations

from hydrolite.gee_catalog.loader import load_catalog


def compare_assets(asset_ids: list[str]) -> list[dict]:
    wanted = {item.lower() for item in asset_ids}
    return [row for row in load_catalog() if row["asset_id"].lower() in wanted]
