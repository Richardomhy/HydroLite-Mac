from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


OFFICIAL_PAGE = "https://developers.google.com/earth-engine/datasets/catalog/"


def normalize_asset_id(value: Any) -> str:
    return str(value or "").strip()


def normalize_dataset_type(value: Any) -> str | None:
    text = str(value or "").lower()
    if "feature" in text or "table" in text: return "FeatureCollection"
    if "collection" in text: return "ImageCollection"
    if "image" in text: return "Image"
    return str(value) if value else None


def normalize_datetime_range(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    props = entry.get("properties", {}) or {}
    start = entry.get("start_datetime") or props.get("start_datetime") or props.get("datetime") or entry.get("start_date")
    end = entry.get("end_datetime") or props.get("end_datetime") or entry.get("end_date")
    return (str(start)[:10] if start else None, str(end)[:10] if end else None)


def normalize_bbox(entry: dict[str, Any]) -> list[float] | None:
    bbox = entry.get("bbox") or (entry.get("extent", {}) or {}).get("spatial", {}).get("bbox", [None])[0]
    if not isinstance(bbox, list) or len(bbox) < 4: return None
    try: return [float(value) for value in bbox[:4]]
    except (TypeError, ValueError): return None


def normalize_bands(entry: dict[str, Any]) -> list[dict[str, Any]]:
    props = entry.get("properties", {}) or {}
    raw = entry.get("bands") or props.get("eo:bands") or entry.get("summaries", {}).get("eo:bands") or []
    if isinstance(raw, dict): raw = [raw]
    units = entry.get("band_units", {}) or props.get("band_units", {}) or {}
    bands = []
    for item in raw:
        if isinstance(item, str): item = {"name": item}
        if not isinstance(item, dict) or not item.get("name"): continue
        bands.append({
            "name": str(item["name"]), "description": item.get("description"), "unit": item.get("unit") or item.get("units") or units.get(str(item["name"])),
            "scale": item.get("scale"), "offset": item.get("offset"),
            # A catalog-level scale is the best available band resolution
            # when an official record does not expose per-band metadata.
            "nominal_scale_m": item.get("nominal_scale_m") or entry.get("nominal_scale_m") or entry.get("nominal_scale"),
            "data_type": item.get("data_type") or item.get("type"), "wavelength": item.get("center_wavelength"),
            "valid_range": item.get("valid_range"), "missing_metadata_fields": [],
        })
    return bands


def normalize_license(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    props = entry.get("properties", {}) or {}
    license_value = entry.get("license") or props.get("license")
    return (str(license_value) if license_value else None, entry.get("license_url") or props.get("license_url"))


def normalize_provider(entry: dict[str, Any]) -> str | None:
    providers = entry.get("providers") or []
    if providers and isinstance(providers[0], dict): return providers[0].get("name")
    return entry.get("provider") or (entry.get("properties", {}) or {}).get("provider")


def build_official_catalog_url(asset_id: str) -> str:
    return OFFICIAL_PAGE + asset_id.replace("/", "_")


def calculate_metadata_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def normalize_stac_catalog_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return normalize_stac_collection(entry)


def normalize_stac_item(entry: dict[str, Any]) -> dict[str, Any]:
    return normalize_stac_collection(entry)


def normalize_stac_collection(entry: dict[str, Any]) -> dict[str, Any]:
    props = entry.get("properties", {}) or {}
    asset_id = normalize_asset_id(entry.get("asset_id") or entry.get("id") or entry.get("collection"))
    start, end = normalize_datetime_range(entry)
    license_text, license_url = normalize_license(entry)
    raw_bands = normalize_bands(entry)
    explicit_bands = entry.get("bands") or []
    if explicit_bands and not raw_bands:
        raw_bands = normalize_bands({"bands": explicit_bands})
    record = {
        "asset_id": asset_id, "catalog_id": entry.get("id"), "title": entry.get("title") or props.get("title") or asset_id or None,
        "description": entry.get("description") or props.get("description"), "dataset_type": normalize_dataset_type(entry.get("dataset_type") or entry.get("type") or props.get("dataset_type")),
        "provider": normalize_provider(entry), "start_date": start, "end_date": end, "bbox": normalize_bbox(entry),
        "temporal_resolution": entry.get("temporal_resolution") or props.get("temporal_resolution"), "nominal_scale_m": entry.get("nominal_scale_m") or entry.get("nominal_scale") or props.get("nominal_scale_m"),
        "projection": entry.get("projection") or props.get("projection"), "bands": raw_bands,
        "keywords": list(entry.get("keywords") or props.get("keywords") or []), "categories": list(entry.get("categories") or props.get("categories") or []),
        "license_text": license_text, "license_url": license_url, "citation": entry.get("citation") or props.get("citation"), "doi": entry.get("doi") or props.get("doi"),
        "official_catalog_url": entry.get("official_catalog_url") or entry.get("official_url") or (build_official_catalog_url(asset_id) if asset_id else None),
        "stac_url": entry.get("stac_url") or entry.get("self_href"), "status": entry.get("status") or "active", "deprecated": bool(entry.get("deprecated", False)),
        "replacement_asset_ids": list(entry.get("replacement_asset_ids") or entry.get("replacement_ids") or []),
        "hydrolite_use_cases": list(entry.get("hydrolite_use_cases") or []), "metadata_quality": "complete",
        # Preserve a supplied source timestamp so loading the same offline
        # snapshot cannot look like a metadata change on every invocation.
        "refresh_time": entry.get("refresh_time") or entry.get("last_refresh") or datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "warnings": [],
    }
    for field in ("asset_id", "title", "dataset_type", "provider", "official_catalog_url", "stac_url"):
        if not record.get(field): record["warnings"].append(f"missing_{field}")
    if not record["bands"]: record["warnings"].append("bands_not_provided")
    record["metadata_quality"] = "complete" if not record["warnings"] else "partial"
    record["source_metadata_hash"] = entry.get("source_metadata_hash") or entry.get("metadata_hash") or calculate_metadata_hash({key: value for key, value in record.items() if key not in {"source_metadata_hash", "refresh_time"}})
    record["official_url"] = record["official_catalog_url"]; record["metadata_hash"] = record["source_metadata_hash"]; record["last_refresh"] = record["refresh_time"]
    return record


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return normalize_stac_collection(record)
