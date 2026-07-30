from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

import pandas as pd

from hydrolite.drought_classification import classify_drought_value


def _current(data: pd.Series | pd.DataFrame, column: str | None = None, name: str = "unknown") -> dict[str, Any]:
    series = data[column] if isinstance(data, pd.DataFrame) and column else data
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {"drought_type": name, "status": "unavailable", "value": None, "class": "unavailable"}
    value = float(values.iloc[-1])
    return {"drought_type": name, "status": "available", "value": value, "class": classify_drought_value(value)}


def assess_current_meteorological_drought(data): return _current(data, name="meteorological")
def assess_current_agricultural_drought(data): return _current(data, name="agricultural")
def assess_current_hydrological_drought(data): return _current(data, name="hydrological")
def assess_current_reservoir_drought(data): return _current(data, name="reservoir")
def assess_current_groundwater_drought(data): return _current(data, name="groundwater")


def calculate_current_composite_status(results: list[dict[str, Any]] | dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = list(results.values()) if isinstance(results, dict) else results
    values = [float(row["value"]) for row in rows if row.get("value") is not None]
    value = sum(values) / len(values) if values else None
    return {"drought_type": "composite", "status": "available" if values else "unavailable", "value": value, "class": classify_drought_value(value), "components": rows}


def compare_current_to_historical_percentiles(results: pd.Series | pd.DataFrame) -> dict[str, Any]:
    series = pd.to_numeric(results.iloc[:, 0] if isinstance(results, pd.DataFrame) else results, errors="coerce").dropna()
    if series.empty:
        return {"status": "unavailable"}
    current = float(series.iloc[-1])
    return {"status": "available", "current": current, "historical_percentile": float((series <= current).mean() * 100)}


def write_current_drought_status(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    analysis_date = pd.Timestamp(result.get("analysis_date", datetime.now(timezone.utc))).tz_localize(None)
    latest = pd.Timestamp(result.get("latest_observation_date", analysis_date)).tz_localize(None)
    latency = int((analysis_date.normalize() - latest.normalize()).days)
    freshness = "current" if latency <= int(result.get("maximum_latency_days", 7)) else "stale_data"
    metadata = {
        **result,
        "analysis_date": str(analysis_date),
        "data_as_of": str(result.get("data_as_of", latest)),
        "latest_observation_date": str(latest),
        "latency_days": latency,
        "freshness_status": freshness,
        "missing_sources": result.get("missing_sources", []),
        "confidence": result.get("confidence", "limited"),
    }
    rows = metadata.get("components", [])
    with pd.ExcelWriter(output / "current_drought_status.xlsx") as writer:
        pd.DataFrame([{key: value for key, value in metadata.items() if key != "components"}]).to_excel(writer, sheet_name="overview", index=False)
        pd.DataFrame(rows).to_excel(writer, sheet_name="components", index=False)
    (output / "current_drought_status.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    zh = output / "current_drought_report_zh.md"
    en = output / "current_drought_report_en.md"
    zh.write_text(
        "# 当前干旱状态\n\n"
        f"- 分析日期：`{analysis_date.date()}`\n- 最新观测：`{latest.date()}`\n- 时效：`{freshness}`（{latency} 日）\n"
        f"- 综合诊断：`{metadata.get('class', 'unavailable')}`\n- 置信度：`{metadata.get('confidence')}`\n\n"
        "该诊断不等于当地法定干旱预警标准；数据过期时不得称为实时状态。\n",
        encoding="utf-8",
    )
    en.write_text(
        "# Current Drought Status\n\n"
        f"- analysis date: `{analysis_date.date()}`\n- latest observation: `{latest.date()}`\n- freshness: `{freshness}` ({latency} days)\n"
        f"- composite diagnostic: `{metadata.get('class', 'unavailable')}`\n- confidence: `{metadata.get('confidence')}`\n\n"
        "This diagnostic is not a statutory drought warning. Stale inputs are not described as real time.\n",
        encoding="utf-8",
    )
    return {"xlsx": output / "current_drought_status.xlsx", "json": output / "current_drought_status.json", "report_zh": zh, "report_en": en}
