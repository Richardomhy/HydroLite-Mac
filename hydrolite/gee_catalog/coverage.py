from __future__ import annotations


def coverage_status(record: dict, start: str | None = None, end: str | None = None, bbox: list[float] | None = None) -> dict:
    return {"temporal_overlap": True if not (start or end) else bool(record.get("start_date")), "bbox_checked": bbox is not None, "spatial_coverage": "metadata_only" if bbox else "not_requested"}
