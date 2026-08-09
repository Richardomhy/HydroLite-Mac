"""Load and manipulate clean-room registry metadata without harvesting sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from hydrolite.research_method_card import ResearchMethodCard
from hydrolite.research_source import ResearchSource


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "research_sources.yaml"
METHODS_PATH = ROOT / "config" / "research_methods.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_source_policy() -> dict[str, Any]:
    return _load_yaml(SOURCES_PATH).get("policy", {})


def list_sources() -> list[ResearchSource]:
    data = _load_yaml(SOURCES_PATH)
    return [ResearchSource.from_dict(row) for row in data.get("sources", []) + data.get("third_party_sources", [])]


def list_methods() -> list[ResearchMethodCard]:
    return [ResearchMethodCard.from_dict(row) for row in _load_yaml(METHODS_PATH).get("methods", [])]


def get_source(source_id: str) -> ResearchSource:
    return next(source for source in list_sources() if source.source_id == source_id)


def get_method(method_id: str) -> ResearchMethodCard:
    return next(card for card in list_methods() if card.method_id == method_id)


def search_sources(query: str) -> list[ResearchSource]:
    needle = query.casefold()
    return [source for source in list_sources() if needle in " ".join([source.source_id, source.title, *source.keywords]).casefold()]


def register_source(source: ResearchSource, records: list[ResearchSource] | None = None) -> list[ResearchSource]:
    current = list_sources() if records is None else list(records)
    if any(item.source_id == source.source_id for item in current):
        raise ValueError(f"Duplicate research source ID: {source.source_id}")
    return [*current, source]


def update_source(source_id: str, changes: dict[str, Any], records: list[ResearchSource] | None = None) -> list[ResearchSource]:
    current = list_sources() if records is None else list(records)
    updated: list[ResearchSource] = []
    found = False
    for source in current:
        if source.source_id == source_id:
            payload = source.as_dict() | changes
            updated.append(ResearchSource.from_dict(payload)); found = True
        else:
            updated.append(source)
    if not found:
        raise KeyError(source_id)
    return updated


def register_method_card(card: ResearchMethodCard, cards: list[ResearchMethodCard] | None = None) -> list[ResearchMethodCard]:
    current = list_methods() if cards is None else list(cards)
    if any(item.method_id == card.method_id for item in current):
        raise ValueError(f"Duplicate method ID: {card.method_id}")
    return [*current, card]


def link_source_to_method(method_id: str, source_id: str, cards: list[ResearchMethodCard] | None = None) -> list[ResearchMethodCard]:
    current = list_methods() if cards is None else list(cards)
    linked: list[ResearchMethodCard] = []
    for card in current:
        if card.method_id == method_id:
            payload = card.as_dict()
            payload["source_ids"] = list(dict.fromkeys([*card.source_ids, source_id]))
            linked.append(ResearchMethodCard.from_dict(payload))
        else:
            linked.append(card)
    return linked


def assess_method_readiness(card: ResearchMethodCard, sources: list[ResearchSource] | None = None) -> dict[str, str]:
    available = {source.source_id: source for source in (list_sources() if sources is None else sources)}
    if any(source_id not in available for source_id in card.source_ids):
        return {"method_id": card.method_id, "readiness": "blocked", "reason": "missing_source_link"}
    if any(source.implementation_mode != "method_inspired_clean_room" for source in (available[item] for item in card.source_ids)):
        return {"method_id": card.method_id, "readiness": "blocked", "reason": "clean_room_required"}
    return {"method_id": card.method_id, "readiness": "clean_room_ready", "reason": "metadata_only_method_card"}


def intake_sources() -> dict[str, object]:
    return {"status": "passed", "sources": [item.as_dict() for item in list_sources()], "reuse": "clean_room_only"}
