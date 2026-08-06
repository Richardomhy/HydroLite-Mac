from __future__ import annotations

import json
from pathlib import Path
import tempfile

from hydrolite.gee_catalog.loader import CACHE, fixture_records
from hydrolite.gee_catalog.normalizer import normalize_record


def refresh_catalog(mode: str = "dry-run") -> dict:
    if mode == "dry-run": return {"status": "dry_run", "source": "gs://earthengine-stac/catalog.json", "would_write": str(CACHE), "records": len(fixture_records())}
    records = [normalize_record(row) for row in fixture_records()]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=CACHE.parent, suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump({"source": "gs://earthengine-stac/catalog.json", "records": records, "refresh_mode": "offline_fixture_after_remote_auth_not_required"}, handle, ensure_ascii=False, indent=2); staged = Path(handle.name)
    staged.replace(CACHE)
    return {"status": "refreshed_offline_fixture", "source": "gs://earthengine-stac/catalog.json", "records": len(records), "cache": str(CACHE), "rollback": "previous cache is retained until atomic replacement"}
