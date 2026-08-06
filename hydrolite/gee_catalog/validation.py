from __future__ import annotations

from hydrolite.gee_catalog.loader import load_catalog
from hydrolite.gee_catalog.schema import validate_record


def validate_catalog() -> dict:
    errors = {row.get("asset_id", "unknown"): validate_record(row) for row in load_catalog()}
    errors = {key: value for key, value in errors.items() if value}
    return {"status": "passed" if not errors else "failed", "records": len(load_catalog()), "errors": errors}
