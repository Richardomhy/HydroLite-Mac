from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import yaml

from hydrolite.gee_catalog.loader import load_catalog_records
from hydrolite.gee_catalog.schema import GeeRelaxedAlternative, GeeSearchRequest


ROOT = Path(__file__).resolve().parents[2]
ALIASES = ROOT / "config" / "data_sources" / "gee_search_aliases.yaml"


def _aliases(query: str) -> set[str]:
    values = {query.lower()}
    if ALIASES.exists():
        for group in yaml.safe_load(ALIASES.read_text(encoding="utf-8")).get("aliases", {}).values():
            terms = {str(item).lower() for item in group}
            if values & terms: values |= terms
    return values


def _text(record: dict) -> str:
    bands = " ".join(item.get("name", "") if isinstance(item, dict) else str(item) for item in record.get("bands", []))
    values = [record.get(key, "") for key in ("asset_id", "title", "description", "dataset_type", "provider", "temporal_resolution", "status")]
    values += record.get("keywords", []) + record.get("categories", []) + record.get("hydrolite_use_cases", []) + [bands]
    return " ".join(str(value) for value in values).lower()


def search_exact_asset_id(asset_id: str, records: Iterable[dict] | None = None) -> list[dict]:
    return [row for row in (records or load_catalog_records()) if str(row.get("asset_id", "")).lower() == asset_id.lower()]


def search_text(query: str, language: str | None = None, records: Iterable[dict] | None = None) -> list[dict]:
    terms = _aliases(query)
    return [row for row in (records or load_catalog_records()) if any(term in _text(row) for term in terms)]


def _contains(record: dict, key: str, value: str) -> bool: return value.lower() in str(record.get(key, "")).lower()
def filter_dataset_type(records, value): return [row for row in records if _contains(row, "dataset_type", value)]
def filter_provider(records, value): return [row for row in records if _contains(row, "provider", value)]
def filter_category(records, value): return [row for row in records if any(value.lower() == str(item).lower() for item in row.get("categories", []))]
def filter_band(records, value): return [row for row in records if any(value.lower() == str(item.get("name", "") if isinstance(item, dict) else item).lower() for item in row.get("bands", []))]
def filter_resolution(records, maximum_m): return [row for row in records if row.get("nominal_scale_m") is not None and float(row["nominal_scale_m"]) <= float(maximum_m)]
def filter_band_resolution(records, maximum_m):
    return [row for row in records if any(
        item.get("nominal_scale_m") is not None and float(item["nominal_scale_m"]) <= float(maximum_m)
        for item in row.get("bands", []) if isinstance(item, dict)
    )]


def filter_date_overlap(records, start, end):
    return [row for row in records if not (row.get("end_date") and str(row["end_date"]) < str(start)) and not (row.get("start_date") and str(row["start_date"]) > str(end))]


def filter_full_temporal_coverage(records, start, end):
    return [row for row in records if (not row.get("start_date") or str(row["start_date"]) <= str(start)) and (not row.get("end_date") or str(row["end_date"]) >= str(end) or str(row["end_date"]).lower() == "present")]


def filter_bbox_envelope(records, bbox):
    west, south, east, north = map(float, bbox)
    return [row for row in records if row.get("bbox") and float(row["bbox"][0]) <= west and float(row["bbox"][1]) <= south and float(row["bbox"][2]) >= east and float(row["bbox"][3]) >= north]


def filter_status(records, status): return [row for row in records if _contains(row, "status", status)]
def filter_deprecated(records, include): return list(records) if include else [row for row in records if not row.get("deprecated", False)]
def filter_license(records, rule): return [row for row in records if rule.lower() in str(row.get("license_text") or row.get("license", "")).lower()]
def filter_use_case(records, model_id): return [row for row in records if any(model_id.lower() in str(value).lower() for value in row.get("hydrolite_use_cases", []))]


def rank_search_results(records: list[dict], request: GeeSearchRequest) -> list[dict]:
    terms = _aliases(request.query or "")
    return sorted(records, key=lambda row: (sum(term in _text(row) for term in terms), not row.get("deprecated", False), row.get("asset_id", "")), reverse=True)


def build_relaxed_alternatives(request: GeeSearchRequest, records: list[dict]) -> list[dict]:
    candidates = search_text(request.query or request.asset_id or "", records=records)[: request.result_limit]
    return [asdict(GeeRelaxedAlternative(str(row.get("asset_id")), ["hard filters removed"], ["runtime_footprint_check_required"], "Does not satisfy every requested hard condition.")) for row in candidates]


def search_catalog(request: GeeSearchRequest | str | None = None, records: list[dict] | None = None, **filters) -> dict:
    request = GeeSearchRequest(query=request, **filters) if isinstance(request, str) else (request or GeeSearchRequest(**filters))
    all_records = list(records if records is not None else load_catalog_records())
    rows = list(all_records)
    if request.asset_id: rows = search_exact_asset_id(request.asset_id, rows)
    if request.query: rows = search_text(request.query, request.language, rows)
    for value, fn in ((request.dataset_type, filter_dataset_type), (request.provider, filter_provider), (request.category, filter_category), (request.band, filter_band), (request.status, filter_status), (request.license_rule, filter_license), (request.use_case, filter_use_case)):
        if value: rows = fn(rows, value)
    if request.maximum_nominal_resolution_m is not None: rows = filter_resolution(rows, request.maximum_nominal_resolution_m)
    if request.maximum_matched_band_resolution_m is not None: rows = filter_band_resolution(rows, request.maximum_matched_band_resolution_m)
    if request.date_start and request.date_end: rows = (filter_full_temporal_coverage if request.full_temporal_coverage else filter_date_overlap)(rows, request.date_start, request.date_end)
    if request.bbox: rows = filter_bbox_envelope(rows, request.bbox)
    rows = filter_deprecated(rows, request.include_deprecated)
    rows = rank_search_results(rows, request)[: request.result_limit]
    relaxed = [] if rows else build_relaxed_alternatives(request, all_records)
    return {"status": "passed" if rows else "no_exact_match", "request": asdict(request), "matches": rows, "records": rows, "relaxed_alternatives": relaxed, "catalog_spatial_semantics": "catalog_envelope_coverage" if request.bbox else "not_requested"}
