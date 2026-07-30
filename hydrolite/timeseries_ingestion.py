from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def detect_timestamp_column(data: pd.DataFrame) -> str | None:
    candidates = ("timestamp", "datetime", "valid_time", "time", "date", "时间", "日期时间", "日期")
    normalized = {str(column).lower(): str(column) for column in data.columns}
    return next((normalized[name] for name in candidates if name in normalized), None)


def parse_timestamp_column(data: pd.DataFrame, column: str, timezone: str | None = None) -> pd.DataFrame:
    frame = data.copy()
    values = frame[column]
    if pd.api.types.is_numeric_dtype(values) and values.dropna().between(20_000, 80_000).all():
        parsed = pd.Timestamp("1899-12-30") + pd.to_timedelta(values, unit="D")
    else:
        normalized = (
            values.astype(str)
            .str.replace("年", "-", regex=False)
            .str.replace("月", "-", regex=False)
            .str.replace("日", "", regex=False)
        )
        parsed = pd.to_datetime(normalized, errors="coerce")
    if timezone:
        parsed = parsed.dt.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT") if parsed.dt.tz is None else parsed.dt.tz_convert(timezone)
    frame[column] = parsed
    return frame


def infer_time_interval(data: pd.DataFrame, column: str | None = None) -> dict[str, Any]:
    name = column or detect_timestamp_column(data)
    if not name:
        return {"status": "timestamp_missing", "interval_seconds": None}
    parsed = pd.to_datetime(data[name], errors="coerce").dropna().sort_values()
    diffs = parsed.diff().dropna().dt.total_seconds()
    if diffs.empty:
        return {"status": "insufficient_data", "interval_seconds": None}
    interval = float(diffs[diffs > 0].min())
    regular = bool((diffs - interval).abs().max() < 1e-6)
    return {"status": "regular" if regular else "irregular", "interval_seconds": interval, "interval_minutes": interval / 60, "regular": regular}


def detect_duplicate_timestamps(data: pd.DataFrame, column: str | None = None) -> list[str]:
    name = column or detect_timestamp_column(data)
    if not name:
        return []
    parsed = pd.to_datetime(data[name], errors="coerce")
    return [str(value) for value in parsed[parsed.duplicated(keep=False)].dropna().unique()]


def detect_missing_timestamps(data: pd.DataFrame, column: str | None = None) -> list[str]:
    name = column or detect_timestamp_column(data)
    interval = infer_time_interval(data, name)
    if not name or not interval.get("interval_seconds"):
        return []
    parsed = pd.to_datetime(data[name], errors="coerce").dropna().sort_values()
    expected = pd.date_range(parsed.min(), parsed.max(), freq=pd.Timedelta(seconds=interval["interval_seconds"]))
    return [str(value) for value in expected.difference(parsed)]


def detect_irregular_interval(data: pd.DataFrame, column: str | None = None) -> bool:
    return infer_time_interval(data, column).get("status") == "irregular"


def detect_timezone(data: pd.DataFrame, column: str | None = None) -> str | None:
    name = column or detect_timestamp_column(data)
    if not name:
        return None
    parsed = pd.to_datetime(data[name], errors="coerce")
    return str(parsed.dt.tz) if parsed.dt.tz is not None else None


def align_timeseries_to_project(data: pd.DataFrame, project_config: dict[str, Any]) -> pd.DataFrame:
    name = detect_timestamp_column(data)
    if not name:
        raise ValueError("Timestamp column is missing.")
    frame = parse_timestamp_column(data, name)
    start, end = pd.Timestamp(project_config["time"]["start"]), pd.Timestamp(project_config["time"]["end"])
    return frame[(frame[name] >= start) & (frame[name] <= end)].reset_index(drop=True)


def aggregate_timeseries(data: pd.DataFrame, interval: str, method: str) -> pd.DataFrame:
    name = detect_timestamp_column(data)
    if not name:
        raise ValueError("Timestamp column is missing.")
    frame = parse_timestamp_column(data, name).set_index(name)
    numeric = frame.select_dtypes("number")
    if method not in {"sum", "mean", "last", "max", "min"}:
        raise ValueError(f"Unsupported aggregation method: {method}")
    return getattr(numeric.resample(interval), method)().reset_index()


def write_timeseries_quality_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "timeseries_quality.json"
    xlsx_path = output / "timeseries_quality.xlsx"
    import json
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    pd.DataFrame([result]).to_excel(xlsx_path, index=False)
    return {"json": json_path, "xlsx": xlsx_path}
