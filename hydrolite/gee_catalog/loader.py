from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data_demo" / "method_inspiration" / "gee_catalog" / "official_metadata_fixture.json"
CACHE = ROOT / ".hydrolite" / "gee_catalog" / "catalog.json"


def fixture_records() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]


def load_catalog() -> list[dict]:
    path = CACHE if CACHE.exists() else FIXTURE
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["records"]
