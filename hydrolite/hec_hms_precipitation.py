from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
from typing import Any

import numpy as np
import pandas as pd

from hydrolite.hec_hms import (
    HMS_PROJECT_NAME,
    PROJECT_ROOT,
    _fatal_hms_lines,
    _file_snapshot,
    _first_hec_hms_executable,
    _jython_unicode_literal,
    _now,
    _resolve,
    _run_hms_script,
    build_hms_open_script,
    build_official_hms_compute_script,
    collect_hydrolite_project_for_hms,
    create_calibrated_hms_project_from_hydrolite,
    discover_hms_run_names,
    run_hms_open_probe,
)
from hydrolite.hec_hms_format import parse_hms_basin_file, parse_hms_control_file, validate_hms_component_syntax


DEFAULT_PRECIPITATION_OUTPUT = PROJECT_ROOT / "output" / "hec_hms_precipitation"
DEFAULT_RAINFALL_PROJECT = PROJECT_ROOT / "output" / "hec_hms_project_rainfall_verified"
GAGE_NAME = "HydroLite_Precip"
PRECIPITATION_DSS_RELATIVE = Path("data") / "hydrolite_precipitation.dss"
CONTEXT_FILE = Path("reports") / "hec_hms_rainfall_context.json"
HEC_MONOLITH_JAR = Path(
    "/Applications/HEC-HMS-4.13.app/Contents/Resources/lib/hec-monolith-3.3.28.jar"
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def load_hydrolite_rainfall_csv(path: str | Path) -> pd.DataFrame:
    source = _resolve(path)
    if not source.is_file():
        raise FileNotFoundError(f"HydroLite rainfall CSV not found: {source}")
    frame = pd.read_csv(source)
    time_column = next((name for name in ("timestamp", "time", "datetime", "date_time") if name in frame.columns), None)
    rainfall_column = next(
        (name for name in ("precipitation_increment_mm", "rainfall_mm", "rain_mm", "rainfall") if name in frame.columns),
        None,
    )
    if time_column is None:
        raise ValueError(f"Rainfall CSV requires a time column: {source}")
    if rainfall_column is None:
        raise ValueError(f"Rainfall CSV requires rainfall_mm or rain_mm: {source}")
    normalized = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(frame[time_column], errors="coerce"),
            "precipitation_increment_mm": pd.to_numeric(frame[rainfall_column], errors="coerce"),
        }
    )
    normalized.attrs["source_path"] = str(source)
    normalized.attrs["source_time_column"] = time_column
    normalized.attrs["source_rainfall_column"] = rainfall_column
    normalized.attrs["source_rows"] = len(frame)
    return normalized


def infer_precipitation_interval(data: pd.DataFrame) -> dict[str, Any]:
    timestamps = pd.to_datetime(data["timestamp"], errors="coerce").dropna().sort_values()
    differences = timestamps.diff().dropna().dt.total_seconds().div(60)
    if differences.empty:
        return {"interval_minutes": None, "regular": False, "differences_minutes": [], "message": "At least two timestamps are required."}
    rounded = differences.round(9)
    interval = float(rounded.mode().iloc[0])
    regular = bool((rounded - interval).abs().le(1e-6).all())
    return {
        "interval_minutes": int(round(interval)) if abs(interval - round(interval)) <= 1e-6 else interval,
        "regular": regular,
        "differences_minutes": [float(value) for value in sorted(rounded.unique())],
        "message": "regular" if regular else "Irregular rainfall intervals require volume-preserving resampling.",
    }


def validate_precipitation_timeseries(data: pd.DataFrame) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    required = {"timestamp", "precipitation_increment_mm"}
    missing_columns = sorted(required - set(data.columns))
    if missing_columns:
        errors.append(f"Missing standardized columns: {', '.join(missing_columns)}")
        return {"status": "failed", "errors": errors, "warnings": warnings, "interval": {}}
    timestamps = pd.to_datetime(data["timestamp"], errors="coerce")
    rainfall = pd.to_numeric(data["precipitation_increment_mm"], errors="coerce")
    if timestamps.isna().any():
        errors.append(f"Unparseable timestamps: {int(timestamps.isna().sum())}")
    if rainfall.isna().any():
        errors.append(f"Missing or non-numeric rainfall values: {int(rainfall.isna().sum())}")
    if (rainfall.dropna() < 0).any():
        errors.append("Rainfall increments must not be negative.")
    if timestamps.duplicated().any():
        errors.append(f"Duplicate timestamps: {int(timestamps.duplicated().sum())}")
    valid_times = timestamps.dropna()
    if not valid_times.is_monotonic_increasing:
        errors.append("Timestamps must be strictly increasing.")
    interval = infer_precipitation_interval(pd.DataFrame({"timestamp": timestamps}))
    if not interval.get("regular"):
        warnings.append(interval.get("message", "Irregular rainfall interval."))
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "interval": interval,
        "record_count": int(len(data)),
        "start": valid_times.min().isoformat() if not valid_times.empty else "",
        "end": valid_times.max().isoformat() if not valid_times.empty else "",
        "total_precipitation_mm": float(rainfall.sum()) if not rainfall.dropna().empty else 0.0,
        "maximum_increment_mm": float(rainfall.max()) if not rainfall.dropna().empty else 0.0,
        "missing_values": int(rainfall.isna().sum()),
    }


def normalize_hms_precipitation_timeseries(
    data: pd.DataFrame,
    interval_minutes: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    source_total = float(pd.to_numeric(data["precipitation_increment_mm"], errors="coerce").sum())
    frame = data[["timestamp", "precipitation_increment_mm"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["precipitation_increment_mm"] = pd.to_numeric(frame["precipitation_increment_mm"], errors="coerce")
    validation = validate_precipitation_timeseries(frame)
    if validation["status"] == "failed":
        raise ValueError("; ".join(validation["errors"]))
    frame = frame.reset_index(drop=True)
    inferred = validation["interval"]
    target_interval = interval_minutes or inferred.get("interval_minutes")
    if not target_interval or float(target_interval) <= 0:
        raise ValueError("A positive precipitation interval could not be inferred.")
    resampled = False
    if not inferred.get("regular") or abs(float(inferred["interval_minutes"]) - float(target_interval)) > 1e-6:
        indexed = frame.set_index("timestamp")["precipitation_increment_mm"]
        target = indexed.resample(f"{int(target_interval)}min", origin=indexed.index[0]).sum(min_count=1).fillna(0.0)
        frame = target.rename("precipitation_increment_mm").reset_index()
        resampled = True
    normalized_total = float(frame["precipitation_increment_mm"].sum())
    difference = normalized_total - source_total
    tolerance = max(1e-9, abs(source_total) * 1e-9)
    report = {
        "status": "passed" if abs(difference) <= tolerance else "failed",
        "source_rows": int(len(data)),
        "normalized_rows": int(len(frame)),
        "interval_minutes": int(target_interval),
        "interval_regular": True,
        "resampled": resampled,
        "source_total_mm": source_total,
        "normalized_total_mm": normalized_total,
        "total_difference_mm": difference,
        "tolerance_mm": tolerance,
        "start": frame["timestamp"].min().isoformat(),
        "end": frame["timestamp"].max().isoformat(),
        "maximum_increment_mm": float(frame["precipitation_increment_mm"].max()),
        "warnings": (["Irregular input was resampled using interval sums; total rainfall was preserved."] if resampled else []),
    }
    if report["status"] == "failed":
        raise ValueError(f"Rainfall total changed during normalization by {difference} mm.")
    frame.attrs.update(data.attrs)
    frame.attrs["normalization"] = report
    return frame, report


def align_precipitation_to_control_window(
    data: pd.DataFrame,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    interval_minutes: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    start_time = pd.Timestamp(start)
    end_time = pd.Timestamp(end)
    if end_time < start_time:
        raise ValueError("Control end must not precede control start.")
    expected = pd.date_range(start_time, end_time, freq=f"{int(interval_minutes)}min")
    indexed = data.set_index("timestamp")["precipitation_increment_mm"]
    aligned = indexed.reindex(expected)
    missing = int(aligned.isna().sum())
    original_total = float(indexed.sum())
    aligned = aligned.fillna(0.0)
    result = aligned.rename("precipitation_increment_mm").rename_axis("timestamp").reset_index()
    difference = float(result["precipitation_increment_mm"].sum()) - original_total
    report = {
        "status": "passed" if abs(difference) <= max(1e-9, abs(original_total) * 1e-9) else "failed",
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "interval_minutes": int(interval_minutes),
        "zero_filled_points": missing,
        "total_before_mm": original_total,
        "total_after_mm": float(result["precipitation_increment_mm"].sum()),
        "total_difference_mm": difference,
        "tail_zero_fill_applied": missing > 0,
    }
    return result, report


def find_project_rainfall_csv(project_dir: str | Path) -> Path:
    project = _resolve(project_dir)
    candidates = [project / "data" / "rainfall.csv"]
    if project.name != "demo_project":
        candidates.append(PROJECT_ROOT / "projects" / "demo_project" / "data" / "rainfall.csv")
    candidates.extend(sorted((PROJECT_ROOT / "data_demo").glob("*rain*.csv")))
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError(f"No rainfall CSV found for project: {project}")


def build_precipitation_dss_pathname(project_name: str, gage_name: str, interval_minutes: int) -> str:
    interval = _dss_interval_label(interval_minutes).upper()
    project = _dss_token(project_name)
    gage = _dss_token(gage_name)
    return f"/{project}/{gage}/PRECIP-INC//{interval}/OBS/"


def _dss_token(value: str) -> str:
    return "_".join(str(value).strip().upper().replace("-", " ").split()) or "HYDROLITE"


def _dss_interval_label(interval_minutes: int) -> str:
    if interval_minutes % 1440 == 0:
        return f"{interval_minutes // 1440}DAY"
    if interval_minutes % 60 == 0:
        return f"{interval_minutes // 60}HOUR"
    return f"{interval_minutes}MIN"


def build_precipitation_gage_definition(
    project_name: str,
    gage_name: str,
    dss_file: str | Path,
    pathname: str,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> str:
    start_time = pd.Timestamp(start) if start is not None else pd.Timestamp("2000-01-01")
    end_time = pd.Timestamp(end) if end is not None else start_time
    now = datetime.now()
    return "\n".join(
        [
            f"Gage Manager: {project_name}",
            f"     Gage Manager: {project_name}",
            "     Version: 4.13",
            "     Filepath Separator: /",
            "End:",
            "",
            f"Gage: {gage_name}",
            f"     Gage: {gage_name}",
            "     Gage Type: Precipitation",
            "     Description: HydroLite incremental precipitation",
            f"     Last Modified Date: {now:%d %B %Y}",
            f"     Last Modified Time: {now:%H:%M:%S}",
            "     Reference Height Units: Meters",
            "     Reference Height: 0",
            "     Data Source Type: External DSS",
            f"     Filename: {Path(dss_file).as_posix()}",
            f"     Pathname: {pathname}",
            "     Variant: Variant-1",
            f"       Start Time: {start_time:%d %B %Y}, {start_time:%H:%M}",
            f"       End Time: {end_time:%d %B %Y}, {end_time:%H:%M}",
            "     End Variant: Variant-1",
            "End:",
            "",
        ]
    )


def detect_dssvue_installation() -> dict[str, Any]:
    candidates = [
        Path("/Applications/HEC-DSSVue.app"),
        Path("/Applications/HEC-DSSVue-3.3.32.app"),
        Path.home() / "Applications" / "HEC-DSSVue.app",
    ]
    existing = [str(path) for path in candidates if path.exists()]
    return {"available": bool(existing), "candidates": [str(path) for path in candidates], "existing": existing}


def detect_hec_dss_java_classes() -> dict[str, Any]:
    classes = {
        "hec.heclib.dss.HecDss": "hec/heclib/dss/HecDss.class",
        "hec.io.TimeSeriesContainer": "hec/io/TimeSeriesContainer.class",
        "hec.heclib.util.HecTime": "hec/heclib/util/HecTime.class",
    }
    found: dict[str, bool] = {name: False for name in classes}
    if HEC_MONOLITH_JAR.is_file():
        import zipfile

        with zipfile.ZipFile(HEC_MONOLITH_JAR) as archive:
            members = set(archive.namelist())
        found = {name: member in members for name, member in classes.items()}
    executable = _first_hec_hms_executable()
    return {
        "available": bool(executable) and all(found.values()),
        "hms_executable": executable or "",
        "jar": str(HEC_MONOLITH_JAR),
        "jar_exists": HEC_MONOLITH_JAR.is_file(),
        "classes": found,
        "script_mode": bool(executable),
    }


def detect_hec_dss_python_backends() -> list[dict[str, Any]]:
    rows = []
    for module in ("pydsstools", "hecdss", "pyhecdss"):
        rows.append({"module": module, "available": importlib.util.find_spec(module) is not None})
    return rows


def detect_hec_dss_write_backends() -> list[dict[str, Any]]:
    java = detect_hec_dss_java_classes()
    dssvue = detect_dssvue_installation()
    python_backends = detect_hec_dss_python_backends()
    return [
        {
            "backend": "hec_hms_java",
            "available": java["available"],
            "executable": java["hms_executable"],
            "jars": [java["jar"]] if java["jar_exists"] else [],
            "java_classes": java["classes"],
            "script_mode": java["script_mode"],
            "read_capability": java["available"],
            "write_capability": java["available"],
            "catalog_capability": java["available"],
            "confidence": "high" if java["available"] else "none",
            "warnings": [],
        },
        {
            "backend": "hec_dssvue",
            "available": dssvue["available"],
            "executable": dssvue["existing"][0] if dssvue["existing"] else "",
            "jars": [],
            "java_classes": {},
            "script_mode": False,
            "read_capability": False,
            "write_capability": False,
            "catalog_capability": False,
            "confidence": "unverified" if dssvue["available"] else "none",
            "warnings": ["DSSVue was detected but its command syntax has not been exercised by HydroLite."],
        },
        {
            "backend": "python",
            "available": any(row["available"] for row in python_backends),
            "executable": os.fspath(Path(sys.executable)),
            "jars": [],
            "java_classes": {},
            "script_mode": False,
            "read_capability": False,
            "write_capability": False,
            "catalog_capability": False,
            "confidence": "unverified" if any(row["available"] for row in python_backends) else "none",
            "warnings": [f"Detected modules, not functionally verified: {python_backends}"],
        },
        {
            "backend": "official_reference_copy",
            "available": False,
            "executable": "",
            "jars": [],
            "java_classes": {},
            "script_mode": False,
            "read_capability": False,
            "write_capability": False,
            "catalog_capability": False,
            "confidence": "none",
            "warnings": ["Disabled: an unrelated official DSS must never be copied and presented as HydroLite rainfall."],
        },
    ]


def recommend_hec_dss_write_backend() -> dict[str, Any]:
    for row in detect_hec_dss_write_backends():
        if row["available"] and row["read_capability"] and row["write_capability"] and row["catalog_capability"]:
            return {"backend": row["backend"], "status": "available", "confidence": row["confidence"], "details": row}
    return {"backend": "unavailable", "status": "unavailable", "confidence": "none", "details": {}}


def write_dss_backend_diagnosis(output_dir: str | Path = DEFAULT_PRECIPITATION_OUTPUT) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "generated_at": _now(),
        "platform": platform.platform(),
        "backends": detect_hec_dss_write_backends(),
        "recommendation": recommend_hec_dss_write_backend(),
    }
    json_path = output / "dss_backend_diagnosis.json"
    md_path = output / "dss_backend_diagnosis.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# HEC-DSS Backend Diagnosis",
        "",
        f"- Recommended backend: `{result['recommendation']['backend']}`",
        f"- Status: `{result['recommendation']['status']}`",
        "",
        "| Backend | Available | Read | Write | Catalog | Confidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {row['backend']} | {row['available']} | {row['read_capability']} | {row['write_capability']} | {row['catalog_capability']} | {row['confidence']} |"
        for row in result["backends"]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def build_dss_precipitation_write_script(
    timeseries: pd.DataFrame,
    dss_path: str | Path,
    pathname: str,
    output_script: str | Path,
) -> Path:
    validation = validate_precipitation_timeseries(timeseries)
    if validation["status"] == "failed" or not validation["interval"].get("regular"):
        raise ValueError("Rainfall must be valid and regular before DSS writing.")
    interval = int(validation["interval"]["interval_minutes"])
    start = pd.Timestamp(timeseries["timestamp"].iloc[0])
    values = [float(value) for value in timeseries["precipitation_increment_mm"]]
    script = _resolve(output_script)
    script.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "# -*- coding: ascii -*-",
            "from hec.heclib.dss import HecDss",
            "from hec.heclib.util import HecTime",
            "from hec.io import TimeSeriesContainer",
            "from jarray import array",
            f"dss_path = {_jython_unicode_literal(_resolve(dss_path))}",
            f"pathname = {pathname!r}",
            f"values = {values!r}",
            f"start = HecTime({start.strftime('%d%b%Y')!r}, {start.strftime('%H%M')!r})",
            "tsc = TimeSeriesContainer()",
            "tsc.fullName = pathname",
            "tsc.setStartTime(start)",
            f"tsc.interval = {interval}",
            "tsc.numberValues = len(values)",
            "tsc.values = array(values, 'd')",
            "tsc.units = 'MM'",
            "tsc.type = 'PER-CUM'",
            "dss = HecDss.open(dss_path)",
            "try:",
            "    dss.put(tsc)",
            "    print 'HYDROLITE_DSS_WRITE_OK|' + pathname",
            "    print 'HYDROLITE_DSS_CATALOG|' + '|'.join([str(item) for item in dss.getCatalogedPathnames()])",
            "finally:",
            "    dss.done()",
        ]
    )
    script.write_text(content + "\n", encoding="ascii")
    return script


def _build_dss_read_script(dss_path: Path, pathname: str, output_script: Path) -> Path:
    output_script.parent.mkdir(parents=True, exist_ok=True)
    output_script.write_text(
        "\n".join(
            [
                "# -*- coding: ascii -*-",
                "from hec.heclib.dss import HecDss",
                f"dss_path = {_jython_unicode_literal(dss_path)}",
                f"pathname = {pathname!r}",
                "dss = HecDss.open(dss_path)",
                "try:",
                "    print 'HYDROLITE_DSS_EXISTS|' + str(dss.recordExists(pathname))",
                "    data = dss.get(pathname)",
                "    print 'HYDROLITE_DSS_NAME|' + str(data.fullName)",
                "    print 'HYDROLITE_DSS_COUNT|' + str(data.numberValues)",
                "    print 'HYDROLITE_DSS_START|' + str(data.getStartTime().dateAndTime())",
                "    print 'HYDROLITE_DSS_END|' + str(data.getEndTime().dateAndTime())",
                "    print 'HYDROLITE_DSS_INTERVAL|' + str(data.interval)",
                "    print 'HYDROLITE_DSS_UNITS|' + str(data.units)",
                "    print 'HYDROLITE_DSS_TYPE|' + str(data.type)",
                "    print 'HYDROLITE_DSS_VALUES|' + ','.join([str(value) for value in data.values])",
                "finally:",
                "    dss.done()",
            ]
        )
        + "\n",
        encoding="ascii",
    )
    return output_script


def _markers(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("HYDROLITE_") and "|" in line:
            key, value = line.split("|", 1)
            result[key] = value
    return result


def write_precipitation_to_dss(
    timeseries: pd.DataFrame,
    dss_path: str | Path,
    pathname: str,
    backend: str = "auto",
    timeout: int = 60,
) -> dict[str, Any]:
    recommended = recommend_hec_dss_write_backend()
    selected = recommended["backend"] if backend == "auto" else backend
    target = _resolve(dss_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if selected != "hec_hms_java" or recommended["status"] != "available":
        return {
            "status": "dss_backend_unavailable",
            "backend": selected,
            "dss_path": str(target),
            "pathname": pathname,
            "error_message": "No verified HEC-DSS write backend is available.",
        }
    target.unlink(missing_ok=True)
    script = build_dss_precipitation_write_script(timeseries, target, pathname, target.parent.parent / "scripts" / "write_precipitation_dss.py")
    attempt = _run_hms_script(script, target.parent, min(timeout, 60))
    text = f"{attempt.get('stdout', '')}\n{attempt.get('stderr', '')}"
    fatal = _fatal_hms_lines(text)
    success = (
        attempt.get("returncode") == 0
        and "HYDROLITE_DSS_WRITE_OK" in text
        and target.is_file()
        and target.stat().st_size > 0
        and not fatal
    )
    return {
        "status": "success" if success else "failed",
        "backend": selected,
        "dss_path": str(target),
        "pathname": pathname,
        "file_size_bytes": target.stat().st_size if target.exists() else 0,
        "returncode": attempt.get("returncode"),
        "runtime_seconds": attempt.get("runtime_seconds", 0.0),
        "fatal_errors": fatal,
        "error_message": "" if success else (attempt.get("stderr") or "DSS write did not satisfy success checks."),
        "attempt": attempt,
        "script": str(script),
    }


def read_back_precipitation_dss_record(dss_path: str | Path, pathname: str) -> dict[str, Any]:
    target = _resolve(dss_path)
    if not target.is_file() or target.stat().st_size == 0:
        return {"status": "failed", "error_message": f"Non-empty DSS file not found: {target}", "values": []}
    script = _build_dss_read_script(target, pathname, target.parent.parent / "scripts" / "read_precipitation_dss.py")
    attempt = _run_hms_script(script, target.parent, 60)
    text = f"{attempt.get('stdout', '')}\n{attempt.get('stderr', '')}"
    markers = _markers(text)
    fatal = _fatal_hms_lines(text)
    try:
        values = [float(value) for value in markers.get("HYDROLITE_DSS_VALUES", "").split(",") if value]
        count = int(markers.get("HYDROLITE_DSS_COUNT", len(values)))
        interval = int(markers.get("HYDROLITE_DSS_INTERVAL", 0))
    except ValueError:
        values, count, interval = [], 0, 0
    success = attempt.get("returncode") == 0 and count > 0 and len(values) == count and not fatal
    raw_record_exists = markers.get("HYDROLITE_DSS_EXISTS", "False").lower() == "true"
    # HEC-DSS recordExists() returns False for a valid time-series pathname whose
    # D-part is intentionally blank. A successful get() with values is the
    # authoritative read-back check for that catalog-spanning pathname.
    readable_record = success and count > 0
    return {
        "status": "success" if success else "failed",
        "dss_path": str(target),
        "pathname": markers.get("HYDROLITE_DSS_NAME", pathname),
        "record_exists": readable_record,
        "record_exists_api": raw_record_exists,
        "record_count": count,
        "start": markers.get("HYDROLITE_DSS_START", ""),
        "end": markers.get("HYDROLITE_DSS_END", ""),
        "interval_minutes": interval,
        "units": markers.get("HYDROLITE_DSS_UNITS", ""),
        "type": markers.get("HYDROLITE_DSS_TYPE", ""),
        "values": values,
        "missing_values": sum(1 for value in values if not np.isfinite(value)),
        "returncode": attempt.get("returncode"),
        "fatal_errors": fatal,
        "error_message": "" if success else (attempt.get("stderr") or "DSS read-back failed."),
        "attempt": attempt,
        "script": str(script),
    }


def compare_csv_and_dss_precipitation(csv_data: pd.DataFrame, dss_data: dict[str, Any]) -> dict[str, Any]:
    csv_values = [float(value) for value in csv_data["precipitation_increment_mm"]]
    dss_values = [float(value) for value in dss_data.get("values", [])]
    csv_total = float(sum(csv_values))
    dss_total = float(sum(dss_values))
    total_difference = dss_total - csv_total
    maximum_difference = (max(dss_values) - max(csv_values)) if dss_values and csv_values else float("nan")
    tolerance = max(1e-8, abs(csv_total) * 1e-8)
    return {
        "status": "passed" if len(csv_values) == len(dss_values) and abs(total_difference) <= tolerance and abs(maximum_difference) <= tolerance else "failed",
        "csv_record_count": len(csv_values),
        "dss_record_count": len(dss_values),
        "csv_total_mm": csv_total,
        "dss_total_mm": dss_total,
        "total_difference_mm": total_difference,
        "csv_maximum_mm": max(csv_values) if csv_values else None,
        "dss_maximum_mm": max(dss_values) if dss_values else None,
        "maximum_difference_mm": maximum_difference,
        "tolerance_mm": tolerance,
    }


def validate_precipitation_dss_record(
    dss_path: str | Path,
    pathname: str,
    expected_timeseries: pd.DataFrame,
) -> dict[str, Any]:
    readback = read_back_precipitation_dss_record(dss_path, pathname)
    comparison = compare_csv_and_dss_precipitation(expected_timeseries, readback)
    expected_validation = validate_precipitation_timeseries(expected_timeseries)
    expected_start = pd.Timestamp(expected_timeseries["timestamp"].iloc[0])
    expected_end = pd.Timestamp(expected_timeseries["timestamp"].iloc[-1])
    actual_start = _parse_hec_datetime(readback.get("start", ""))
    actual_end = _parse_hec_datetime(readback.get("end", ""))
    checks = {
        "pathname_exists": bool(readback.get("record_exists")),
        "record_count_matches": comparison["csv_record_count"] == comparison["dss_record_count"],
        "start_matches": actual_start == expected_start,
        "end_matches": actual_end == expected_end,
        "interval_matches": readback.get("interval_minutes") == expected_validation["interval"].get("interval_minutes"),
        "units_match": str(readback.get("units", "")).upper() == "MM",
        "type_match": str(readback.get("type", "")).upper() == "PER-CUM",
        "total_matches": abs(comparison["total_difference_mm"]) <= comparison["tolerance_mm"],
        "maximum_matches": abs(comparison["maximum_difference_mm"]) <= comparison["tolerance_mm"],
        "missing_values_zero": readback.get("missing_values", 0) == 0,
    }
    return {
        "status": "passed" if readback["status"] == "success" and all(checks.values()) else "failed",
        "rainfall_dss_ready": readback["status"] == "success" and all(checks.values()),
        "checks": checks,
        "readback": readback,
        "comparison": comparison,
    }


def _parse_hec_datetime(value: str) -> pd.Timestamp | None:
    match = re.fullmatch(r"\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4}),\s*(\d{1,2}):(\d{2})\s*", value)
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    hour_value = int(hour)
    base = pd.Timestamp(f"{day} {month} {year} {hour_value % 24:02d}:{minute}")
    return base + pd.Timedelta(days=1) if hour_value == 24 else base


def _build_catalog_script(dss_path: Path, output_script: Path) -> Path:
    output_script.parent.mkdir(parents=True, exist_ok=True)
    output_script.write_text(
        "\n".join(
            [
                "# -*- coding: ascii -*-",
                "from hec.heclib.dss import HecDss",
                f"dss_path = {_jython_unicode_literal(dss_path)}",
                "dss = HecDss.open(dss_path)",
                "try:",
                "    print 'HYDROLITE_DSS_CATALOG|' + '|'.join([str(item) for item in dss.getCatalogedPathnames()])",
                "finally:",
                "    dss.done()",
            ]
        )
        + "\n",
        encoding="ascii",
    )
    return output_script


def catalog_dss_file(dss_path: str | Path) -> dict[str, Any]:
    target = _resolve(dss_path)
    if not target.is_file() or target.stat().st_size == 0:
        return {"status": "unavailable", "dss_path": str(target), "pathnames": [], "error_message": "DSS file is missing or empty."}
    script = _build_catalog_script(target, target.parent / ".hydrolite_scripts" / f"catalog_{target.stem}.py")
    attempt = _run_hms_script(script, target.parent, 60)
    markers = _markers(f"{attempt.get('stdout', '')}\n{attempt.get('stderr', '')}")
    pathnames = [item for item in markers.get("HYDROLITE_DSS_CATALOG", "").split("|") if item]
    return {
        "status": "success" if attempt.get("returncode") == 0 and pathnames else "failed",
        "dss_path": str(target),
        "file_size_bytes": target.stat().st_size,
        "pathnames": pathnames,
        "pathname_count": len(pathnames),
        "returncode": attempt.get("returncode"),
        "error_message": "" if pathnames else (attempt.get("stderr") or "No DSS pathnames were returned."),
        "attempt": attempt,
    }


def classify_hms_dss_pathnames(catalog: dict[str, Any] | list[str]) -> list[dict[str, Any]]:
    pathnames = catalog if isinstance(catalog, list) else catalog.get("pathnames", [])
    rows: list[dict[str, Any]] = []
    for pathname in pathnames:
        upper = pathname.upper()
        if "PRECIP-INC" in upper:
            category = "precipitation_input"
        elif "FLOW" in upper and "SUBBASIN" in upper:
            category = "subbasin_outflow"
        elif "FLOW" in upper and "REACH" in upper:
            category = "reach_outflow"
        elif "FLOW" in upper and any(token in upper for token in ("JUNCTION", "SINK", "OUTLET")):
            category = "sink_or_outlet_flow"
        elif "FLOW" in upper:
            category = "flow"
        elif "BASIN" in upper and "AVERAGE" in upper:
            category = "basin_average"
        elif "LOSS" in upper:
            category = "loss"
        elif "EXCESS" in upper:
            category = "excess_precipitation"
        else:
            category = "unknown"
        rows.append({"pathname": pathname, "category": category})
    return rows


def find_hms_flow_pathnames(catalog: dict[str, Any] | list[str]) -> list[str]:
    return [row["pathname"] for row in classify_hms_dss_pathnames(catalog) if "flow" in row["category"]]


def find_hms_precipitation_pathnames(catalog: dict[str, Any] | list[str]) -> list[str]:
    return [row["pathname"] for row in classify_hms_dss_pathnames(catalog) if row["category"] == "precipitation_input"]


def find_hms_basin_result_pathnames(catalog: dict[str, Any] | list[str]) -> list[str]:
    return [row["pathname"] for row in classify_hms_dss_pathnames(catalog) if row["category"] not in {"precipitation_input", "unknown"}]


def generate_hms_precipitation_gage(
    project_dir: str | Path,
    gage_name: str,
    dss_file: str | Path,
    pathname: str,
    precipitation_data: pd.DataFrame | None = None,
) -> Path:
    root = _resolve(project_dir)
    start = precipitation_data["timestamp"].min() if precipitation_data is not None else None
    end = precipitation_data["timestamp"].max() if precipitation_data is not None else None
    path = root / f"{HMS_PROJECT_NAME}.gage"
    path.write_text(build_precipitation_gage_definition(HMS_PROJECT_NAME, gage_name, dss_file, pathname, start, end), encoding="utf-8")
    return path


def _basin_subbasin_names(project_dir: Path) -> list[str]:
    basin_path = next(iter(sorted(project_dir.glob("*.basin"))), None)
    if not basin_path:
        return []
    parsed = parse_hms_basin_file(basin_path)
    return [block["name"] for block in parsed["blocks"] if block["block_type"] == "Subbasin"]


def link_precipitation_gage_to_meteorologic_model(project_dir: str | Path, gage_name: str) -> Path:
    root = _resolve(project_dir)
    met_path = next(iter(sorted(root.glob("*.met"))), None)
    if not met_path:
        raise FileNotFoundError(f"Meteorologic model not found: {root}")
    lines = met_path.read_text(encoding="utf-8", errors="replace").splitlines()
    header_end = next((index for index, line in enumerate(lines) if line.strip() == "End:"), None)
    if header_end is None:
        raise ValueError(f"Meteorologic header is not closed: {met_path}")
    header = lines[: header_end + 1]
    updated_header = []
    for line in header:
        if line.strip().startswith("Precipitation Method:"):
            updated_header.append("     Precipitation Method: Weighted Gages")
        else:
            updated_header.append(line)
    body = [
        "",
        f"Gage: {gage_name}",
        "     Type: Recording",
        "End:",
        "",
        "Precip Method Parameters: Weighted Gages",
        "     Use HEC1 Weighting Scheme: No",
        "     Use Indexing: No",
        "     Allow Depth Override: No",
        "End:",
    ]
    for subbasin in _basin_subbasin_names(root):
        body.extend(
            [
                "",
                f"Subbasin: {subbasin}",
                f"     Gage: {gage_name}",
                "     Volume Weight: 1",
                "     Temporal Distribution Weight: 1",
                "End:",
            ]
        )
    met_path.write_text("\n".join(updated_header + body) + "\n", encoding="utf-8")
    return met_path


def link_meteorologic_model_to_subbasins(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    met_path = next(iter(sorted(root.glob("*.met"))), None)
    subbasins = _basin_subbasin_names(root)
    text = met_path.read_text(encoding="utf-8", errors="replace") if met_path else ""
    mapped = [name for name in subbasins if f"Subbasin: {name}" in text]
    return {"subbasins": subbasins, "mapped_subbasins": mapped, "unmapped_subbasins": sorted(set(subbasins) - set(mapped))}


def validate_hms_gage_references(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    gage_path = root / f"{HMS_PROJECT_NAME}.gage"
    context = read_rainfall_context(root)
    text = gage_path.read_text(encoding="utf-8", errors="replace") if gage_path.exists() else ""
    checks = {
        "gage_file_exists": gage_path.is_file(),
        "gage_name_defined": f"Gage: {context.get('gage_name', GAGE_NAME)}" in text,
        "dss_file_referenced": str(context.get("dss_relative_path", PRECIPITATION_DSS_RELATIVE)).replace("\\", "/") in text,
        "pathname_referenced": context.get("pathname", "") in text,
        "external_dss_defined": "Data Source Type: External DSS" in text,
    }
    return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "gage_file": str(gage_path)}


def validate_hms_meteorologic_precipitation(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    met_path = next(iter(sorted(root.glob("*.met"))), None)
    text = met_path.read_text(encoding="utf-8", errors="replace") if met_path else ""
    linkage = link_meteorologic_model_to_subbasins(root)
    checks = {
        "meteorologic_file_exists": bool(met_path and met_path.is_file()),
        "weighted_gages_method": "Precipitation Method: Weighted Gages" in text,
        "single_recording_gage": text.count("Type: Recording") == 1,
        "all_subbasins_linked": bool(linkage["subbasins"]) and not linkage["unmapped_subbasins"],
        "weights_defined": text.count("Volume Weight: 1") == len(linkage["subbasins"]),
    }
    return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, **linkage, "meteorologic_file": str(met_path or "")}


def synchronize_hms_control_with_precipitation(project_dir: str | Path, precipitation_data: pd.DataFrame) -> Path:
    root = _resolve(project_dir)
    control_path = next(iter(sorted(root.glob("*.control"))), None)
    if not control_path:
        raise FileNotFoundError(f"Control file not found: {root}")
    validation = validate_precipitation_timeseries(precipitation_data)
    interval = int(validation["interval"]["interval_minutes"])
    start = pd.Timestamp(precipitation_data["timestamp"].min())
    end = pd.Timestamp(precipitation_data["timestamp"].max())
    date_text = datetime.now().strftime("%d %B %Y").lstrip("0")
    control_path.write_text(
        "\n".join(
            [
                "Control: hydrolite_control",
                "     Description: Control synchronized to HydroLite precipitation",
                f"     Last Modified Date: {date_text}",
                f"     Last Modified Time: {datetime.now():%H:%M:%S}",
                "     Version: 4.13",
                f"     Start Date: {start:%d %B %Y}",
                f"     Start Time: {start:%H:%M}",
                f"     End Date: {end:%d %B %Y}",
                f"     End Time: {end:%H:%M}",
                f"     Time Interval: {interval}",
                "End:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return control_path


def validate_hms_control_window(project_dir: str | Path, precipitation_data: pd.DataFrame) -> dict[str, Any]:
    root = _resolve(project_dir)
    control_path = next(iter(sorted(root.glob("*.control"))), None)
    if not control_path:
        return {"status": "failed", "checks": {}, "error_message": "Control file not found."}
    parsed = parse_hms_control_file(control_path)
    properties = next(block["property_map"] for block in parsed["blocks"] if block["block_type"] == "Control")
    start = pd.to_datetime(f"{properties.get('Start Date', [''])[0]} {properties.get('Start Time', [''])[0]}", errors="coerce")
    end = pd.to_datetime(f"{properties.get('End Date', [''])[0]} {properties.get('End Time', [''])[0]}", errors="coerce")
    rainfall_start = pd.Timestamp(precipitation_data["timestamp"].min())
    rainfall_end = pd.Timestamp(precipitation_data["timestamp"].max())
    checks = {
        "start_within_rainfall": pd.notna(start) and start >= rainfall_start,
        "end_within_rainfall": pd.notna(end) and end <= rainfall_end,
        "start_matches": pd.notna(start) and start == rainfall_start,
        "end_matches": pd.notna(end) and end == rainfall_end,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": {key: bool(value) for key, value in checks.items()},
        "control_start": start.isoformat() if pd.notna(start) else "",
        "control_end": end.isoformat() if pd.notna(end) else "",
        "rainfall_start": rainfall_start.isoformat(),
        "rainfall_end": rainfall_end.isoformat(),
    }


def validate_hms_simulation_timestep(project_dir: str | Path, interval_minutes: int) -> dict[str, Any]:
    root = _resolve(project_dir)
    control_path = next(iter(sorted(root.glob("*.control"))), None)
    if not control_path:
        return {"status": "failed", "interval_minutes": interval_minutes, "control_interval_minutes": None}
    parsed = parse_hms_control_file(control_path)
    properties = next(block["property_map"] for block in parsed["blocks"] if block["block_type"] == "Control")
    control_interval = int(float(properties.get("Time Interval", [0])[0]))
    compatible = control_interval > 0 and interval_minutes % control_interval == 0
    return {
        "status": "passed" if compatible else "failed",
        "interval_minutes": interval_minutes,
        "control_interval_minutes": control_interval,
        "compatible": compatible,
    }


def write_precipitation_mapping_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "hec_hms_precipitation_mapping.json"
    md_path = output / "hec_hms_precipitation_mapping.md"
    xlsx_path = output / "hec_hms_precipitation_mapping.xlsx"
    safe = _json_safe(result)
    json_path.write_text(json.dumps(safe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.DataFrame([safe.get("overview", safe)]).to_excel(xlsx_path, index=False)
    overview = safe.get("overview", safe)
    lines = ["# HEC-HMS Precipitation Mapping", ""]
    for key, value in overview.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in safe.get("warnings", []))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "xlsx": xlsx_path}


def write_precipitation_dss_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "hec_hms_precipitation_dss.json"
    md_path = output / "hec_hms_precipitation_dss.md"
    safe = _json_safe(result)
    json_path.write_text(json.dumps(safe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# HEC-HMS Precipitation DSS",
                "",
                f"- Write status: `{safe.get('write', {}).get('status', 'not_run')}`",
                f"- Read-back status: `{safe.get('validation', {}).get('status', 'not_run')}`",
                f"- DSS: `{safe.get('write', {}).get('dss_path', '')}`",
                f"- Pathname: `{safe.get('write', {}).get('pathname', '')}`",
                f"- Total difference (mm): `{safe.get('validation', {}).get('comparison', {}).get('total_difference_mm', '')}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path}


def validate_hms_precipitation_mapping(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    context = read_rainfall_context(root)
    normalized_path = Path(context.get("normalized_rainfall_csv", ""))
    precipitation = pd.read_csv(normalized_path, parse_dates=["timestamp"]) if normalized_path.is_file() else pd.DataFrame()
    gage = validate_hms_gage_references(root)
    meteorology = validate_hms_meteorologic_precipitation(root)
    control = validate_hms_control_window(root, precipitation) if not precipitation.empty else {"status": "failed"}
    timestep = validate_hms_simulation_timestep(root, int(context.get("interval_minutes", 0)))
    result = {
        "status": "passed" if all(item.get("status") == "passed" for item in (gage, meteorology, control, timestep)) else "failed",
        "gage": gage,
        "meteorology": meteorology,
        "control": control,
        "timestep": timestep,
        "overview": {
            "gage_name": context.get("gage_name", GAGE_NAME),
            "dss_file": context.get("dss_relative_path", ""),
            "pathname": context.get("pathname", ""),
            "interval_minutes": context.get("interval_minutes"),
            "units": "MM",
            "type": "PER-CUM",
            "meteorologic_method": "Weighted Gages",
            "subbasin_count": len(meteorology.get("subbasins", [])),
            "mapped_subbasins": ", ".join(meteorology.get("mapped_subbasins", [])),
            "unmapped_subbasins": ", ".join(meteorology.get("unmapped_subbasins", [])),
            "control_window": f"{control.get('control_start', '')} to {control.get('control_end', '')}",
            "rainfall_total_mm": context.get("total_precipitation_mm"),
        },
        "warnings": [],
    }
    result["reports"] = {key: str(path) for key, path in write_precipitation_mapping_report(root / "reports", result).items()}
    return result


def read_rainfall_context(project_dir: str | Path) -> dict[str, Any]:
    path = _resolve(project_dir) / CONTEXT_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_rainfall_context(project_dir: str | Path, context: dict[str, Any]) -> Path:
    path = _resolve(project_dir) / CONTEXT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(context), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def create_hms_rainfall_verified_project(
    hydrolite_project_dir: str | Path,
    output_dir: str | Path = DEFAULT_RAINFALL_PROJECT,
) -> dict[str, Any]:
    root = _resolve(output_dir)
    calibrated = create_calibrated_hms_project_from_hydrolite(hydrolite_project_dir, root)
    (root / "data").mkdir(exist_ok=True)
    rainfall_path = find_project_rainfall_csv(hydrolite_project_dir)
    loaded = load_hydrolite_rainfall_csv(rainfall_path)
    normalized, normalization = normalize_hms_precipitation_timeseries(loaded)
    normalized_path = root / "data" / "hydrolite_rainfall_normalized.csv"
    normalized.to_csv(normalized_path, index=False, date_format="%Y-%m-%d %H:%M:%S")
    interval = int(normalization["interval_minutes"])
    pathname = build_precipitation_dss_pathname(HMS_PROJECT_NAME, GAGE_NAME, interval)
    dss_path = root / PRECIPITATION_DSS_RELATIVE
    write_result = write_precipitation_to_dss(normalized, dss_path, pathname)
    dss_validation = validate_precipitation_dss_record(dss_path, pathname, normalized) if write_result["status"] == "success" else {
        "status": "failed",
        "rainfall_dss_ready": False,
        "error_message": write_result.get("error_message", "DSS write failed."),
    }
    generate_hms_precipitation_gage(root, GAGE_NAME, PRECIPITATION_DSS_RELATIVE, pathname, normalized)
    link_precipitation_gage_to_meteorologic_model(root, GAGE_NAME)
    synchronize_hms_control_with_precipitation(root, normalized)
    open_script = build_hms_open_script(root, root / "scripts" / "open_rainfall_verified_project.py")
    run_names = discover_hms_run_names(root)
    compute_script = build_official_hms_compute_script(
        root,
        run_names[0],
        root / "scripts" / "compute_rainfall_verified_project.py",
    ) if run_names else None
    context = {
        "created_at": _now(),
        "source_project_dir": str(_resolve(hydrolite_project_dir)),
        "rainfall_csv": str(rainfall_path),
        "source_rows": int(loaded.attrs.get("source_rows", len(loaded))),
        "normalized_rows": len(normalized),
        "normalized_rainfall_csv": str(normalized_path),
        "interval_minutes": interval,
        "start": normalization["start"],
        "end": normalization["end"],
        "total_precipitation_mm": normalization["normalized_total_mm"],
        "maximum_increment_mm": normalization["maximum_increment_mm"],
        "normalization": normalization,
        "gage_name": GAGE_NAME,
        "dss_relative_path": PRECIPITATION_DSS_RELATIVE.as_posix(),
        "dss_path": str(dss_path),
        "pathname": pathname,
        "dss_backend": write_result.get("backend", "unavailable"),
        "dss_write": write_result,
        "dss_validation": dss_validation,
        "calibrated": calibrated,
        "scripts": {"open": str(open_script), "compute": str(compute_script or "")},
    }
    write_rainfall_context(root, context)
    mapping = validate_hms_precipitation_mapping(root)
    dss_reports = write_precipitation_dss_report(root / "reports", {"write": write_result, "validation": dss_validation})
    context["mapping"] = mapping
    context["dss_reports"] = {key: str(path) for key, path in dss_reports.items()}
    write_rainfall_context(root, context)
    ready = write_result["status"] == "success" and dss_validation["status"] == "passed" and mapping["status"] == "passed"
    status = "ready_for_open_probe" if ready else (
        "dss_backend_unavailable" if write_result["status"] == "dss_backend_unavailable" else "rainfall_mapping_failed"
    )
    return {
        "status": status,
        "project_dir": str(root),
        "context": context,
        "mapping": mapping,
    }


def write_project_rainfall_dss(
    hydrolite_project_dir: str | Path,
    hms_project_dir: str | Path,
) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"HEC-HMS project does not exist: {root}")
    rainfall_path = find_project_rainfall_csv(hydrolite_project_dir)
    loaded = load_hydrolite_rainfall_csv(rainfall_path)
    normalized, normalization = normalize_hms_precipitation_timeseries(loaded)
    normalized_path = root / "data" / "hydrolite_rainfall_normalized.csv"
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(normalized_path, index=False, date_format="%Y-%m-%d %H:%M:%S")
    interval = int(normalization["interval_minutes"])
    pathname = build_precipitation_dss_pathname(HMS_PROJECT_NAME, GAGE_NAME, interval)
    dss_path = root / PRECIPITATION_DSS_RELATIVE
    write_result = write_precipitation_to_dss(normalized, dss_path, pathname)
    validation = (
        validate_precipitation_dss_record(dss_path, pathname, normalized)
        if write_result["status"] == "success"
        else {"status": "failed", "rainfall_dss_ready": False, "error_message": write_result.get("error_message", "")}
    )
    context = read_rainfall_context(root)
    context.update(
        {
            "rainfall_csv": str(rainfall_path),
            "source_rows": int(loaded.attrs.get("source_rows", len(loaded))),
            "normalized_rows": len(normalized),
            "normalized_rainfall_csv": str(normalized_path),
            "interval_minutes": interval,
            "start": normalization["start"],
            "end": normalization["end"],
            "total_precipitation_mm": normalization["normalized_total_mm"],
            "maximum_increment_mm": normalization["maximum_increment_mm"],
            "normalization": normalization,
            "gage_name": GAGE_NAME,
            "dss_relative_path": PRECIPITATION_DSS_RELATIVE.as_posix(),
            "dss_path": str(dss_path),
            "pathname": pathname,
            "dss_backend": write_result.get("backend", "unavailable"),
            "dss_write": write_result,
            "dss_validation": validation,
        }
    )
    write_rainfall_context(root, context)
    reports = write_precipitation_dss_report(root / "reports", {"write": write_result, "validation": validation})
    return {"status": validation.get("status"), "write": write_result, "validation": validation, "reports": reports}


def validate_project_rainfall_dss(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    context = read_rainfall_context(root)
    normalized_path = Path(context.get("normalized_rainfall_csv", ""))
    if not normalized_path.is_file():
        raise FileNotFoundError(f"Normalized rainfall CSV not found: {normalized_path}")
    timeseries = pd.read_csv(normalized_path, parse_dates=["timestamp"])
    result = validate_precipitation_dss_record(context["dss_path"], context["pathname"], timeseries)
    context["dss_validation"] = result
    write_rainfall_context(root, context)
    write_precipitation_dss_report(root / "reports", {"write": context.get("dss_write", {}), "validation": result})
    return result


def map_project_rainfall(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    context = read_rainfall_context(root)
    normalized_path = Path(context.get("normalized_rainfall_csv", ""))
    if not normalized_path.is_file():
        raise FileNotFoundError(f"Normalized rainfall CSV not found: {normalized_path}")
    precipitation = pd.read_csv(normalized_path, parse_dates=["timestamp"])
    generate_hms_precipitation_gage(
        root,
        context.get("gage_name", GAGE_NAME),
        context.get("dss_relative_path", PRECIPITATION_DSS_RELATIVE.as_posix()),
        context["pathname"],
        precipitation,
    )
    link_precipitation_gage_to_meteorologic_model(root, context.get("gage_name", GAGE_NAME))
    synchronize_hms_control_with_precipitation(root, precipitation)
    result = validate_hms_precipitation_mapping(root)
    context["mapping"] = result
    write_rainfall_context(root, context)
    return result


def run_hms_rainfall_open_probe(project_dir: str | Path, timeout: int = 60) -> dict[str, Any]:
    root = _resolve(project_dir)
    result = run_hms_open_probe(root, timeout)
    source_script = Path(result["script"])
    target_script = root / "scripts" / "open_rainfall_verified_project.py"
    if source_script.exists() and source_script != target_script:
        shutil.copy2(source_script, target_script)
    output = root / "reports" / "hec_hms_rainfall_open_probe.json"
    output.write_text(json.dumps(_json_safe(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def evaluate_hms_rainfall_gate(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    context = read_rainfall_context(root)
    normalized_path = Path(context.get("normalized_rainfall_csv", ""))
    precipitation = pd.read_csv(normalized_path, parse_dates=["timestamp"]) if normalized_path.is_file() else pd.DataFrame()
    validation = validate_precipitation_timeseries(precipitation) if not precipitation.empty else {"status": "failed", "interval": {"regular": False}}
    mapping = validate_hms_precipitation_mapping(root)
    open_path = root / "reports" / "hec_hms_rainfall_open_probe.json"
    open_result = json.loads(open_path.read_text(encoding="utf-8")) if open_path.is_file() else {}
    syntax = validate_hms_component_syntax(root)
    dss_validation = context.get("dss_validation", {})
    checks = {
        "rainfall_csv_valid": validation.get("status") == "passed",
        "interval_regular": bool(validation.get("interval", {}).get("regular")),
        "control_window_aligned": mapping.get("control", {}).get("status") == "passed",
        "dss_backend_available": context.get("dss_backend") == "hec_hms_java",
        "precipitation_dss_written": context.get("dss_write", {}).get("status") == "success" and Path(context.get("dss_path", "")).is_file(),
        "precipitation_dss_readback_valid": dss_validation.get("status") == "passed",
        "gage_defined": mapping.get("gage", {}).get("status") == "passed",
        "met_method_defined": mapping.get("meteorology", {}).get("checks", {}).get("weighted_gages_method", False),
        "all_subbasins_linked": mapping.get("meteorology", {}).get("checks", {}).get("all_subbasins_linked", False),
        "run_references_valid": syntax.get("status") == "passed" and bool(discover_hms_run_names(root)),
        "project_opened": open_result.get("status") == "project_opened",
        "no_fatal_errors": not open_result.get("fatal_errors", ["open probe not run"]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "passed" if not failed else "failed",
        "rainfall_ready": not failed,
        "project_dir": str(root),
        "checks": checks,
        "failed_checks": failed,
        "warnings": [f"Rainfall gate failed: {name}" for name in failed],
        "context": context,
        "mapping": mapping,
        "open_result": open_result,
    }


def write_hms_rainfall_gate_report(project_dir: str | Path, result: dict[str, Any] | None = None) -> dict[str, Path]:
    root = _resolve(project_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    gate = result or evaluate_hms_rainfall_gate(root)
    json_path = reports / "hec_hms_rainfall_gate.json"
    md_path = reports / "hec_hms_rainfall_gate.md"
    xlsx_path = reports / "hec_hms_rainfall_gate.xlsx"
    safe = _json_safe(gate)
    json_path.write_text(json.dumps(safe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = [{"check": name, "passed": passed} for name, passed in gate["checks"].items()]
    pd.DataFrame(rows).to_excel(xlsx_path, index=False)
    lines = ["# HEC-HMS Rainfall Gate", "", f"- Status: `{gate['status']}`", f"- Rainfall ready: `{gate['rainfall_ready']}`", ""]
    lines.extend(f"- [{'x' if row['passed'] else ' '}] {row['check']}" for row in rows)
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in gate.get("warnings", []))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "xlsx": xlsx_path}


def run_hms_rainfall_compute(project_dir: str | Path, timeout: int = 120) -> dict[str, Any]:
    root = _resolve(project_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    gate = evaluate_hms_rainfall_gate(root)
    write_hms_rainfall_gate_report(root, gate)
    context = read_rainfall_context(root)
    run_names = discover_hms_run_names(root)
    run_name = run_names[0] if run_names else ""
    script = build_official_hms_compute_script(root, run_name, root / "scripts" / "compute_rainfall_verified_project.py") if run_name else None
    before = _file_snapshot(root)
    attempt = _run_hms_script(script, root, min(timeout, 120)) if gate["rainfall_ready"] and script else None
    after = _file_snapshot(root)
    changed = [name for name, metadata in after.items() if before.get(name) != metadata]
    text = f"{(attempt or {}).get('stdout', '')}\n{(attempt or {}).get('stderr', '')}"
    log_text = text
    for path in root.glob("*.log"):
        log_text += "\n" + path.read_text(encoding="utf-8", errors="replace")
    fatal = _fatal_hms_lines(log_text)
    result_dss = root / "hydrolite_run.dss"
    result_catalog = catalog_dss_file(result_dss) if result_dss.is_file() and result_dss.stat().st_size > 0 else {
        "status": "unavailable",
        "pathnames": [],
        "dss_path": str(result_dss),
    }
    flow_pathnames = find_hms_flow_pathnames(result_catalog)
    if not gate["rainfall_ready"]:
        status = "dss_backend_unavailable" if not gate["checks"].get("dss_backend_available") else "gate_failed"
    elif attempt and attempt.get("timed_out"):
        status = "compute_timeout"
    elif (
        attempt
        and attempt.get("returncode") == 0
        and "HYDROLITE_HMS_COMPUTE_RETURNED" in text
        and not fatal
        and result_dss.is_file()
        and result_dss.stat().st_size > 0
        and flow_pathnames
    ):
        status = "compute_completed"
    else:
        status = "compute_failed"
    result = {
        "status": status,
        "validation_level": "compute_completed" if status == "compute_completed" else ("compute_attempted" if attempt else "run_discovered"),
        "project_dir": str(root),
        "run_name": run_name,
        "rainfall_ready": gate["rainfall_ready"],
        "gate": gate,
        "execute_requested": True,
        "compute_executed": attempt is not None,
        "returncode": (attempt or {}).get("returncode"),
        "runtime_seconds": (attempt or {}).get("runtime_seconds", 0.0),
        "fatal_errors": fatal,
        "warnings": gate.get("warnings", []) + ([] if flow_pathnames or not attempt else ["No flow pathname was found in the result DSS."]),
        "attempt": attempt,
        "changed_files": [str(root / name) for name in changed],
        "changed_dss_files": [str(root / name) for name in changed if Path(name).suffix.lower() == ".dss"],
        "result_dss": str(result_dss),
        "result_dss_nonempty": result_dss.is_file() and result_dss.stat().st_size > 0,
        "result_catalog": result_catalog,
        "flow_pathnames": flow_pathnames,
        "process_cleanup_confirmed": bool((attempt or {}).get("process_terminated")) if attempt else True,
        "script": str(script or ""),
        "rainfall_context": context,
    }
    json_path = reports / "hec_hms_rainfall_compute.json"
    md_path = reports / "hec_hms_rainfall_compute.md"
    xlsx_path = reports / "hec_hms_rainfall_compute_summary.xlsx"
    json_path.write_text(json.dumps(_json_safe(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    overview = {
        "status": status,
        "validation_level": result["validation_level"],
        "run_name": run_name,
        "returncode": result["returncode"],
        "runtime_seconds": result["runtime_seconds"],
        "result_dss": result["result_dss"],
        "result_dss_nonempty": result["result_dss_nonempty"],
        "pathname_count": result_catalog.get("pathname_count", 0),
        "flow_pathname_count": len(flow_pathnames),
        "fatal_error_count": len(fatal),
    }
    with pd.ExcelWriter(xlsx_path) as writer:
        pd.DataFrame([overview]).to_excel(writer, sheet_name="overview", index=False)
        pd.DataFrame(classify_hms_dss_pathnames(result_catalog)).to_excel(writer, sheet_name="pathnames", index=False)
    md_path.write_text(
        "\n".join(["# HEC-HMS Rainfall Compute", ""] + [f"- {key}: `{value}`" for key, value in overview.items()] + ["", "No compute success is reported unless a non-empty result DSS and flow pathname are both observed."])
        + "\n",
        encoding="utf-8",
    )
    return result


def write_hms_result_catalog_report(project_dir: str | Path, catalog: dict[str, Any] | None = None) -> dict[str, Path]:
    root = _resolve(project_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    result_dss = root / "hydrolite_run.dss"
    result = catalog or catalog_dss_file(result_dss)
    classified = classify_hms_dss_pathnames(result)
    flow = find_hms_flow_pathnames(result)
    payload = {**result, "classified": classified, "flow_pathnames": flow, "flow_pathname_count": len(flow)}
    json_path = reports / "hec_hms_result_catalog.json"
    md_path = reports / "hec_hms_result_catalog.md"
    xlsx_path = reports / "hec_hms_result_catalog.xlsx"
    json_path.write_text(json.dumps(_json_safe(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.DataFrame(classified, columns=["pathname", "category"]).to_excel(xlsx_path, index=False)
    lines = [
        "# HEC-HMS Result DSS Catalog",
        "",
        f"- DSS: `{result_dss}`",
        f"- Pathname count: `{len(classified)}`",
        f"- Flow pathname count: `{len(flow)}`",
        "- Deep DSS reading: `not performed`",
        "",
        "| Category | Pathname |",
        "| --- | --- |",
    ]
    lines.extend(f"| {row['category']} | {row['pathname']} |" for row in classified)
    if not flow:
        lines.extend(["", "WARNING: no simulated flow pathname was discovered; none was fabricated."])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "xlsx": xlsx_path}


def write_rainfall_validation_summary(project_dir: str | Path) -> dict[str, Path]:
    root = _resolve(project_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    context = read_rainfall_context(root)
    gate_path = reports / "hec_hms_rainfall_gate.json"
    compute_path = reports / "hec_hms_rainfall_compute.json"
    catalog_path = reports / "hec_hms_result_catalog.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.is_file() else evaluate_hms_rainfall_gate(root)
    compute = json.loads(compute_path.read_text(encoding="utf-8")) if compute_path.is_file() else {}
    catalog = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.is_file() else {}
    overview = {
        "project_dir": str(root),
        "rainfall_csv": context.get("rainfall_csv", ""),
        "record_count": context.get("normalized_rows", 0),
        "interval_minutes": context.get("interval_minutes"),
        "total_precipitation_mm": context.get("total_precipitation_mm"),
        "rainfall_gate": gate.get("status", "not_run"),
        "compute_status": compute.get("status", "not_run"),
        "validation_level": compute.get("validation_level", "run_discovered"),
        "result_dss": compute.get("result_dss", ""),
        "pathname_count": catalog.get("pathname_count", len(catalog.get("classified", []))),
        "flow_pathname_count": catalog.get("flow_pathname_count", 0),
    }
    json_path = reports / "hec_hms_rainfall_validation_summary.json"
    md_path = reports / "hec_hms_rainfall_validation_summary.md"
    xlsx_path = reports / "hec_hms_rainfall_validation_summary.xlsx"
    json_path.write_text(json.dumps({"overview": overview, "context": context, "gate": gate, "compute": compute}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.DataFrame([overview]).to_excel(xlsx_path, index=False)
    md_path.write_text("\n".join(["# HEC-HMS Rainfall Validation Summary", ""] + [f"- {key}: `{value}`" for key, value in overview.items()]) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "xlsx": xlsx_path}


def write_normalized_rainfall_report(project_dir: str | Path, output_dir: str | Path = DEFAULT_PRECIPITATION_OUTPUT) -> dict[str, Any]:
    rainfall_path = find_project_rainfall_csv(project_dir)
    loaded = load_hydrolite_rainfall_csv(rainfall_path)
    normalized, report = normalize_hms_precipitation_timeseries(loaded)
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "hydrolite_rainfall_normalized.csv"
    json_path = output / "hydrolite_rainfall_normalization.json"
    normalized.to_csv(csv_path, index=False, date_format="%Y-%m-%d %H:%M:%S")
    payload = {"rainfall_csv": str(rainfall_path), **report, "normalized_csv": str(csv_path)}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {**payload, "report_json": str(json_path)}
