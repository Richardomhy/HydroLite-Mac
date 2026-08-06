from __future__ import annotations

REQUIRED_FIELDS = {"asset_id", "title", "dataset_type", "provider", "status", "official_url", "stac_url", "metadata_hash", "last_refresh"}


def validate_record(record: dict) -> list[str]:
    return sorted(field for field in REQUIRED_FIELDS if field not in record)
