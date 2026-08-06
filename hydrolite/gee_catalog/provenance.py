from __future__ import annotations


def catalog_provenance() -> dict:
    return {"source": "gs://earthengine-stac/catalog.json", "mode": "offline metadata fixture and explicit refresh", "html_mirroring": False, "third_party_skill_reused": False}
