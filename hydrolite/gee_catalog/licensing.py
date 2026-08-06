from __future__ import annotations


def license_status(record: dict) -> dict:
    return {"asset_id": record["asset_id"], "license": record.get("license", "not_specified"), "citation": record.get("citation", "not_specified")}
