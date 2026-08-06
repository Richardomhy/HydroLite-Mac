from __future__ import annotations


def explain_record(record: dict) -> str:
    return f"{record['asset_id']}: {record['title']} ({record['provider']}); use cases: {', '.join(record.get('hydrolite_use_cases', []))}."
