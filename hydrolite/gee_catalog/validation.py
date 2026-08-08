from __future__ import annotations

import random
from pathlib import Path
from typing import Iterable

import yaml

from hydrolite.gee_catalog.index import build_catalog_index, validate_catalog_index
from hydrolite.gee_catalog.loader import load_catalog_records, load_catalog_manifest
from hydrolite.gee_catalog.schema import validate_record


OFFICIAL_HOSTS = ("storage.googleapis.com", "developers.google.com")
ROOT = Path(__file__).resolve().parents[2]


def validate_catalog_manifest(manifest: dict) -> list[str]:
    required = {"source_url", "source_type", "retrieval_time", "record_count", "validation_status"}
    return sorted(required - set(manifest)) if manifest.get("status") != "fixture_only" else []


def validate_unique_asset_ids(records: Iterable[dict]) -> list[str]:
    values = [str(row.get("asset_id", "")).lower() for row in records]
    return sorted({value for value in values if not value or values.count(value) > 1})


def validate_official_sources(records: Iterable[dict]) -> list[str]:
    bad = []
    for row in records:
        for key in ("official_catalog_url", "official_url", "stac_url"):
            url = str(row.get(key) or "")
            if url and not any(host in url for host in OFFICIAL_HOSTS) and not url.startswith("gs://earthengine-stac/"):
                bad.append(str(row.get("asset_id", "unknown"))); break
    return sorted(set(bad))


def validate_required_fields(records: Iterable[dict]) -> dict[str, list[str]]:
    return {str(row.get("asset_id", "unknown")): missing for row in records if (missing := validate_record(row))}


def validate_dates(records: Iterable[dict]) -> list[str]:
    return [str(row.get("asset_id")) for row in records if row.get("start_date") and row.get("end_date") and str(row["start_date"]) > str(row["end_date"])]


def validate_bbox(records: Iterable[dict]) -> list[str]:
    return [str(row.get("asset_id")) for row in records if row.get("bbox") is not None and (not isinstance(row["bbox"], list) or len(row["bbox"]) != 4)]


def validate_bands(records: Iterable[dict]) -> list[str]:
    return [str(row.get("asset_id")) for row in records if not isinstance(row.get("bands", []), list)]


def validate_index(index, records: Iterable[dict]) -> list[str]:
    return validate_catalog_index(index)


def validate_random_samples(records: list[dict], count: int = 3, seed: int = 42) -> list[str]:
    if not records: return ["empty_catalog"]
    sample = random.Random(seed).sample(records, min(count, len(records)))
    return [str(row.get("asset_id", "unknown")) for row in sample if not row.get("asset_id")]


def classify_catalog_validation(result: dict) -> str:
    if result.get("record_count", 0) == 0: return "invalid"
    if result.get("errors"): return "invalid"
    return "valid_with_warnings" if result.get("warnings") else "valid"


def validate_clean_room_policy() -> list[str]:
    policy = yaml.safe_load((ROOT / "config" / "research_sources.yaml").read_text(encoding="utf-8"))
    source = policy["third_party_sources"][0]
    return [] if policy["policy"]["clean_room_required"] and not source["copy_allowed"] and not source["runtime_dependency_allowed"] else ["m0_clean_room_policy_not_enforced"]


def validate_catalog(records: list[dict] | None = None, manifest: dict | None = None) -> dict:
    rows = list(records if records is not None else load_catalog_records())
    manifest = manifest if manifest is not None else load_catalog_manifest()
    errors = {"duplicate_asset_ids": validate_unique_asset_ids(rows), "required_fields": validate_required_fields(rows), "official_sources": validate_official_sources(rows), "invalid_dates": validate_dates(rows), "invalid_bbox": validate_bbox(rows), "invalid_bands": validate_bands(rows), "index": validate_index(build_catalog_index(rows), rows), "clean_room_policy": validate_clean_room_policy()}
    errors = {key: value for key, value in errors.items() if value}
    warnings = {"manifest": validate_catalog_manifest(manifest), "sample": validate_random_samples(rows)}
    warnings = {key: value for key, value in warnings.items() if value}
    result = {"record_count": len(rows), "errors": errors, "warnings": warnings, "fixture_only": manifest.get("status") == "fixture_only"}
    result["status"] = "fixture_only" if result["fixture_only"] and not errors else classify_catalog_validation(result)
    return result
