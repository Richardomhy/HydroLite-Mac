from __future__ import annotations

from hydrolite.gee_catalog.loader import load_catalog


def search_catalog(query: str, records: list[dict] | None = None, **filters) -> dict:
    query = query.lower().strip(); rows = records or load_catalog()
    def text(row): return " ".join([str(row.get(key, "")) for key in ("asset_id", "title", "description", "dataset_type", "provider", "bands", "hydrolite_use_cases")]).lower()
    matched = [row for row in rows if query in text(row)]
    for field, value in filters.items():
        if value not in (None, ""):
            matched = [row for row in matched if str(value).lower() in str(row.get(field, "")).lower()]
    relaxed = [] if matched else [row for row in rows if any(word in text(row) for word in query.replace("-", " ").split())]
    return {"status": "passed", "query": query, "matches": matched, "no_exact_match": not bool(matched), "relaxed_alternatives": relaxed, "relaxed_conditions": ["keyword token match"] if relaxed and not matched else []}
