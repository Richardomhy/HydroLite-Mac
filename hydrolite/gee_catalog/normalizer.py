from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def normalize_record(record: dict) -> dict:
    result = dict(record); result.setdefault("bands", []); result.setdefault("hydrolite_use_cases", [])
    result.setdefault("metadata_hash", hashlib.sha256(repr(sorted(result.items())).encode()).hexdigest())
    result.setdefault("last_refresh", datetime.now(timezone.utc).isoformat())
    return result
