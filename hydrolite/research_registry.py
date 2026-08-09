"""Compatibility facade for the configuration-backed research registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hydrolite.research_intake import get_source as _get_source, list_sources
from hydrolite.research_reporting import write_research_reports
from hydrolite.research_status import CLEAN_ROOM_NOTICE


NOTICE = CLEAN_ROOM_NOTICE


def built_in_sources() -> list[dict[str, Any]]:
    return [source.as_dict() for source in list_sources()]


def get_source(source_id: str) -> dict[str, Any]:
    return _get_source(source_id).as_dict()


def write_research_outputs(output_dir: str | Path = "output/research_methods") -> dict[str, Path]:
    return write_research_reports(output_dir)
