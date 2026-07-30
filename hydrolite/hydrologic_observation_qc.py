from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


QC_COLUMNS = [
    "dataset", "check_name", "status", "severity", "message", "row_count",
    "affected_count", "processing_status",
]


def _as_frame(data: Any) -> pd.DataFrame:
    return data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)


def _column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in frame), None)


def _check(data: Any, variable: str, value_names: tuple[str, ...], allow_negative: bool = False) -> dict[str, Any]:
    frame = _as_frame(data)
    time_col = _column(frame, ("timestamp", "datetime", "time"))
    value_col = _column(frame, value_names)
    rows: list[dict[str, Any]] = []

    def add(name: str, status: str, message: str, affected: int = 0, severity: str = "warning") -> None:
        rows.append({
            "dataset": variable, "check_name": name, "status": status, "severity": severity,
            "message": message, "row_count": len(frame), "affected_count": int(affected),
            "processing_status": "unchanged",
        })

    if time_col is None:
        add("time_column", "failed", "Missing timestamp/datetime/time column.", len(frame), "fatal")
    if value_col is None:
        add("value_column", "failed", f"Missing one of {value_names}.", len(frame), "fatal")
    if time_col is None or value_col is None:
        return {"status": "rejected", "checks": pd.DataFrame(rows, columns=QC_COLUMNS), "corrections": pd.DataFrame()}

    times = pd.to_datetime(frame[time_col], errors="coerce")
    values = pd.to_numeric(frame[value_col], errors="coerce")
    missing = int(times.isna().sum() + values.isna().sum())
    duplicates = int(times.duplicated(keep=False).sum())
    negative = int((values < 0).sum()) if not allow_negative else 0
    add("missing_values", "passed" if not missing else "warning", f"{missing} missing/unparseable values.", missing)
    add("duplicate_timestamps", "passed" if not duplicates else "warning", f"{duplicates} duplicate timestamps.", duplicates)
    add("non_negative", "passed" if not negative else "failed", f"{negative} negative values.", negative, "fatal" if negative else "info")
    diffs = times.sort_values().diff().dropna().dt.total_seconds()
    irregular = int((diffs != diffs.median()).sum()) if len(diffs) else 0
    add("regular_interval", "passed" if not irregular else "warning", f"{irregular} irregular intervals.", irregular)
    spikes = detect_sensor_spikes(frame, value_col)
    add("sensor_spikes", "passed" if spikes.empty else "warning", f"{len(spikes)} potential spikes retained for review.", len(spikes))
    flat = detect_flatline_periods(frame, value_col)
    add("flatline", "passed" if flat.empty else "warning", f"{len(flat)} flatline rows retained for review.", len(flat))
    peak_missing = 0
    if values.notna().any():
        peak = int(values.idxmax())
        lo, hi = max(0, peak - 1), min(len(frame), peak + 2)
        peak_missing = int(frame.iloc[lo:hi][value_col].isna().sum())
    add("peak_window_coverage", "passed" if not peak_missing else "failed", f"{peak_missing} missing values near peak.", peak_missing, "fatal" if peak_missing else "info")
    status = classify_observation_quality({"checks": pd.DataFrame(rows), "coverage": float(values.notna().mean()) if len(values) else 0})
    return {
        "status": status,
        "checks": pd.DataFrame(rows, columns=QC_COLUMNS),
        "corrections": pd.DataFrame(columns=["row", "timestamp", "original_value", "corrected_value", "method", "reason", "confidence", "manual_confirmation"]),
        "coverage": float(values.notna().mean()) if len(values) else 0.0,
        "value_column": value_col,
        "time_column": time_col,
    }


def validate_rainfall_observations(data: Any) -> dict[str, Any]:
    return _check(data, "rainfall_observed", ("rainfall_mm", "rain_mm", "precipitation_mm"))


def validate_streamflow_observations(data: Any) -> dict[str, Any]:
    return _check(data, "streamflow_observed", ("flow_cms", "observed_streamflow_m3s", "outflow_cms"))


def validate_stage_observations(data: Any) -> dict[str, Any]:
    result = _check(data, "water_level_observed", ("stage_m", "water_level_m"), allow_negative=True)
    discontinuity = detect_datum_changes(_as_frame(data))
    if not discontinuity.empty:
        result["checks"] = pd.concat([result["checks"], pd.DataFrame([{
            "dataset": "water_level_observed", "check_name": "datum_change", "status": "warning",
            "severity": "warning", "message": f"{len(discontinuity)} possible datum changes.",
            "row_count": len(_as_frame(data)), "affected_count": len(discontinuity), "processing_status": "unchanged",
        }])], ignore_index=True)
        result["status"] = classify_observation_quality(result)
    return result


def validate_reservoir_observations(data: Any) -> dict[str, Any]:
    return _check(data, "reservoir_operation_observations", ("storage_m3", "reservoir_storage_m3", "stage_m"), allow_negative=False)


def detect_sensor_spikes(data: Any, value_column: str | None = None, z_threshold: float = 6.0) -> pd.DataFrame:
    frame = _as_frame(data)
    column = value_column or _column(frame, ("flow_cms", "stage_m", "rainfall_mm", "value"))
    if not column or len(frame) < 5:
        return frame.iloc[0:0].copy()
    values = pd.to_numeric(frame[column], errors="coerce")
    delta = values.diff()
    median = delta.median()
    mad = (delta - median).abs().median()
    if not pd.notna(mad) or mad == 0:
        return frame.iloc[0:0].copy()
    mask = (delta - median).abs() > z_threshold * 1.4826 * mad
    return frame.loc[mask.fillna(False)].copy()


def detect_flatline_periods(data: Any, value_column: str | None = None, minimum_length: int = 6) -> pd.DataFrame:
    frame = _as_frame(data)
    column = value_column or _column(frame, ("flow_cms", "stage_m", "rainfall_mm", "value"))
    if not column or frame.empty:
        return frame.iloc[0:0].copy()
    values = pd.to_numeric(frame[column], errors="coerce")
    groups = values.ne(values.shift()).cumsum()
    sizes = groups.map(groups.value_counts())
    return frame.loc[(sizes >= minimum_length) & values.notna()].copy()


def detect_rating_curve_discontinuity(data: Any) -> pd.DataFrame:
    frame = _as_frame(data)
    if not {"stage_m", "flow_cms"}.issubset(frame):
        return frame.iloc[0:0].copy()
    stage = pd.to_numeric(frame["stage_m"], errors="coerce")
    flow = pd.to_numeric(frame["flow_cms"], errors="coerce")
    ratio = flow.diff().abs() / stage.diff().abs().replace(0, np.nan)
    threshold = ratio.median() + 8 * ratio.sub(ratio.median()).abs().median()
    return frame.loc[(ratio > threshold).fillna(False)].copy()


def detect_unit_changes(data: Any) -> pd.DataFrame:
    frame = _as_frame(data)
    if "unit" not in frame:
        return frame.iloc[0:0].copy()
    return frame.loc[frame["unit"].astype(str).ne(frame["unit"].astype(str).shift()) & frame.index.to_series().ne(frame.index.min())].copy()


def detect_datum_changes(data: Any) -> pd.DataFrame:
    frame = _as_frame(data)
    if "datum" not in frame:
        return frame.iloc[0:0].copy()
    return frame.loc[frame["datum"].astype(str).ne(frame["datum"].astype(str).shift()) & frame.index.to_series().ne(frame.index.min())].copy()


def detect_clock_shift(data: Any) -> pd.DataFrame:
    frame = _as_frame(data)
    time_col = _column(frame, ("timestamp", "datetime", "time"))
    if not time_col:
        return frame.iloc[0:0].copy()
    times = pd.to_datetime(frame[time_col], errors="coerce")
    diffs = times.diff().dt.total_seconds()
    expected = diffs[diffs > 0].median()
    return frame.loc[(diffs > 1.5 * expected).fillna(False)].copy() if pd.notna(expected) else frame.iloc[0:0].copy()


def calculate_observation_coverage(data: Any, event: dict[str, Any]) -> float:
    frame = _as_frame(data)
    time_col = _column(frame, ("timestamp", "datetime", "time"))
    value_col = next((name for name in frame.columns if name not in {time_col, "event_id", "station_id", "unit", "source", "quality_flag", "synthetic_demo"} and pd.api.types.is_numeric_dtype(pd.to_numeric(frame[name], errors="coerce"))), None)
    if not time_col or not value_col:
        return 0.0
    times = pd.to_datetime(frame[time_col], errors="coerce")
    mask = times.between(pd.Timestamp(event["warmup_start"]), pd.Timestamp(event["analysis_end"]))
    return float(pd.to_numeric(frame.loc[mask, value_col], errors="coerce").notna().mean()) if mask.any() else 0.0


def classify_observation_quality(result: dict[str, Any]) -> str:
    checks = result.get("checks", pd.DataFrame())
    coverage = float(result.get("coverage", 0))
    if not checks.empty and ((checks["status"] == "failed") & (checks["severity"] == "fatal")).any():
        return "rejected"
    if coverage < 0.7:
        return "insufficient_coverage"
    if not checks.empty and checks["status"].isin(["warning", "failed"]).any():
        return "accepted_with_warnings"
    return "accepted"


def write_observation_qc_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    checks = result.get("checks", pd.DataFrame(columns=QC_COLUMNS))
    corrections = result.get("corrections", pd.DataFrame())
    xlsx = output / "observation_qc_summary.xlsx"
    with pd.ExcelWriter(xlsx) as writer:
        checks.to_excel(writer, sheet_name="checks", index=False)
        corrections.to_excel(writer, sheet_name="corrections", index=False)
    paths = {"xlsx": xlsx}
    for language, title in (("zh", "水文观测质量检查"), ("en", "Hydrologic Observation Quality Control")):
        path = output / f"observation_qc_report_{language}.md"
        path.write_text(
            f"# {title}\n\n- Status: `{result.get('status', 'unknown')}`\n"
            f"- Coverage: `{result.get('coverage', 0):.2%}`\n"
            "- Suspect observations are retained; corrections require an audit record and manual confirmation.\n",
            encoding="utf-8",
        )
        paths[language] = path
    return paths
