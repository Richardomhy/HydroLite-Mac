from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _records(events: Any) -> list[dict[str, Any]]:
    if isinstance(events, pd.DataFrame):
        return events.to_dict("records")
    return [dict(item) for item in events]


def split_events_chronologically(events: Any, config: dict[str, Any] | None = None) -> dict[str, list[str]]:
    rows = sorted(_records(events), key=lambda item: pd.Timestamp(item["rainfall_start"]))
    accepted = [item for item in rows if item.get("quality_status") not in {"rejected", "insufficient_coverage"}]
    ids = [str(item["event_id"]) for item in accepted]
    if len(ids) < 3:
        return {"calibration": ids, "validation": [], "test": [], "strategy": "chronological", "independent_test": False}
    if len(ids) < 5:
        validation_count = 1
        test_count = 0
    else:
        validation_count = max(1, round(len(ids) * float((config or {}).get("validation_fraction", 0.25))))
        test_count = max(1, round(len(ids) * float((config or {}).get("test_fraction", 0.2))))
    calibration_end = len(ids) - validation_count - test_count
    return {
        "calibration": ids[:calibration_end],
        "validation": ids[calibration_end:len(ids) - test_count if test_count else None],
        "test": ids[-test_count:] if test_count else [],
        "strategy": "chronological",
        "independent_test": bool(test_count),
    }


def split_events_by_hydrologic_regime(events: Any, config: dict[str, Any] | None = None) -> dict[str, list[str]]:
    rows = _records(events)
    rows.sort(key=lambda item: (float(item.get("total_rainfall_mm") or 0), pd.Timestamp(item["rainfall_start"])))
    ordered = rows[::2] + rows[1::2]
    return split_events_chronologically(ordered, config)


def split_events_by_magnitude(events: Any, config: dict[str, Any] | None = None) -> dict[str, list[str]]:
    rows = sorted(_records(events), key=lambda item: float(item.get("peak_flow_cms") or 0))
    return split_events_chronologically(rows, config)


def split_events_leave_one_event_out(events: Any) -> list[dict[str, Any]]:
    ids = [str(item["event_id"]) for item in _records(events)]
    return [{"fold": index + 1, "calibration": [item for item in ids if item != held], "validation": [held], "test": []} for index, held in enumerate(ids)]


def detect_event_leakage(split: dict[str, Any]) -> list[str]:
    groups = {name: set(split.get(name, [])) for name in ("calibration", "validation", "test")}
    errors = []
    for left, right in (("calibration", "validation"), ("calibration", "test"), ("validation", "test")):
        overlap = sorted(groups[left] & groups[right])
        if overlap:
            errors.append(f"{left}/{right} overlap: {', '.join(overlap)}")
    return errors


def validate_event_split(split: dict[str, Any]) -> dict[str, Any]:
    errors = detect_event_leakage(split)
    if not split.get("calibration"):
        errors.append("calibration set is empty")
    warnings = []
    if not split.get("test"):
        warnings.append("Fewer than five accepted events or no independent test event.")
    return {"status": "passed" if not errors else "failed", "errors": errors, "warnings": warnings}


def write_event_split_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    yaml_path = output / "event_split.yaml"
    yaml_path.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    validation = validate_event_split(result)
    paths = {"yaml": yaml_path}
    for language, title in (("zh", "洪水事件划分报告"), ("en", "Flood Event Split Report")):
        path = output / f"event_split_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Strategy: `{result.get('strategy')}`\n"
            f"- Calibration: `{', '.join(result.get('calibration', []))}`\n"
            f"- Validation: `{', '.join(result.get('validation', []))}`\n"
            f"- Test: `{', '.join(result.get('test', [])) or 'not established'}`\n"
            f"- Leakage check: `{validation['status']}`\n"
            "- Events and time steps are never randomly shuffled.\n",
            encoding="utf-8",
        )
        paths[language] = path
    return paths
