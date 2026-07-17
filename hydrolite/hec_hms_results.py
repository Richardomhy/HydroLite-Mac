from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
from typing import Any
import zipfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hydrolite.flood_metrics import calculate_event_flow_metrics, compare_event_flow_metrics, validate_event_metrics
from hydrolite.hec_hms import _fatal_hms_lines, _jython_unicode_literal, _resolve, _run_hms_script
from hydrolite.hec_hms_format import parse_hms_basin_file
from hydrolite.hec_hms_precipitation import catalog_dss_file
from hydrolite.metrics import calculate_all_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "output" / "hec_hms_results"
DEFAULT_COMPARISON_DIR = PROJECT_ROOT / "output" / "hec_hms_comparison"
FLOW_UNIT_FACTORS_TO_CMS = {
    "CMS": 1.0,
    "M3/S": 1.0,
    "M^3/S": 1.0,
    "CFS": 0.028316846592,
    "FT3/S": 0.028316846592,
    "FT^3/S": 0.028316846592,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if not isinstance(value, (str, bytes, list, tuple, dict)):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    return value


def _pathname_parts(pathname: str) -> list[str]:
    text = str(pathname).strip()
    if not text.startswith("/") or not text.endswith("/"):
        raise ValueError(f"DSS pathname must start and end with '/': {pathname}")
    parts = text[1:-1].split("/")
    if len(parts) != 6:
        raise ValueError(f"DSS pathname must contain six parts: {pathname}")
    return parts


def parse_dss_pathname(pathname: str) -> dict[str, Any]:
    a_part, b_part, c_part, d_part, e_part, f_part = _pathname_parts(pathname)
    classification = classify_hms_result_pathname(pathname)
    return {
        "pathname": pathname,
        "a_part": a_part,
        "b_part": b_part,
        "c_part": c_part,
        "d_part": d_part,
        "e_part": e_part,
        "f_part": f_part,
        "element_name": b_part,
        "parameter": c_part,
        "interval": e_part,
        "run_name": f_part.removeprefix("RUN:"),
        **classification,
    }


def classify_hms_result_pathname(pathname: str) -> dict[str, Any]:
    _, element, parameter, _, interval, run = _pathname_parts(pathname)
    upper = parameter.upper().replace("_", "-")
    warnings: list[str] = []
    probable_units = "unknown"
    flow_semantics = "not_flow"
    confidence = "high"
    if "PRECIP" in upper and "EXCESS" in upper:
        result_class = "excess_precipitation"
        probable_units = "depth"
    elif "PRECIP" in upper and "LOSS" in upper:
        result_class = "loss"
        probable_units = "depth"
    elif "PRECIP" in upper:
        result_class = "precipitation"
        probable_units = "depth"
    elif "FLOW" in upper:
        probable_units = "flow_or_volume"
        if "UNIT GRAPH" in upper:
            result_class = "unit_hydrograph_pattern"
            flow_semantics = "response_pattern"
            confidence = "medium"
        elif "CUMULATIVE" in upper or upper.endswith("-CUM"):
            result_class = "cumulative_flow"
            flow_semantics = "cumulative_volume"
            probable_units = "volume"
        elif "VOLUME" in upper:
            result_class = "flow_volume"
            flow_semantics = "volume"
            probable_units = "volume"
        elif "AVERAGE" in upper or "MEAN" in upper:
            result_class = "average_flow"
            flow_semantics = "average_flow"
        elif "DIRECT" in upper:
            result_class = "direct_flow"
            flow_semantics = "instantaneous_flow"
        elif "BASE" in upper:
            result_class = "baseflow"
            flow_semantics = "instantaneous_flow"
        elif "ROUTED" in upper:
            result_class = "routed_flow"
            flow_semantics = "instantaneous_flow"
        elif "INFLOW" in upper:
            result_class = "inflow"
            flow_semantics = "instantaneous_flow"
        elif "OUTFLOW" in upper:
            result_class = "outflow"
            flow_semantics = "instantaneous_flow"
        elif upper == "FLOW" or upper in {"FLOW-COMBINE", "FLOW-LOSS"}:
            result_class = "instantaneous_flow"
            flow_semantics = "instantaneous_flow"
        else:
            result_class = "other_flow"
            flow_semantics = "unconfirmed_flow_type"
            confidence = "medium"
            warnings.append("Parameter contains FLOW but its temporal semantics are not confirmed.")
    elif "LOSS" in upper or "INFILTRATION" in upper:
        result_class = "loss"
        probable_units = "depth"
    else:
        result_class = "other"
        confidence = "medium"
    if not element:
        warnings.append("B-part element name is blank.")
        confidence = "low"
    return {
        "result_class": result_class,
        "flow_semantics": flow_semantics,
        "probable_units": probable_units,
        "confidence": confidence,
        "warnings": warnings,
        "element_name": element,
        "parameter": parameter,
        "interval": interval,
        "run_name": run.removeprefix("RUN:"),
    }


def classify_hms_result_catalog(catalog: dict[str, Any] | list[str]) -> list[dict[str, Any]]:
    pathnames = catalog if isinstance(catalog, list) else catalog.get("pathnames", [])
    rows: list[dict[str, Any]] = []
    for pathname in pathnames:
        try:
            rows.append(parse_dss_pathname(pathname))
        except ValueError as exc:
            rows.append(
                {
                    "pathname": pathname,
                    "result_class": "invalid_pathname",
                    "confidence": "none",
                    "warnings": [str(exc)],
                }
            )
    return rows


def find_hms_flow_pathnames(catalog: dict[str, Any] | list[str]) -> list[str]:
    return [
        row["pathname"]
        for row in classify_hms_result_catalog(catalog)
        if row.get("flow_semantics") != "not_flow"
    ]


def find_hms_precipitation_pathnames(catalog: dict[str, Any] | list[str]) -> list[str]:
    return [row["pathname"] for row in classify_hms_result_catalog(catalog) if row.get("result_class") == "precipitation"]


def find_hms_loss_pathnames(catalog: dict[str, Any] | list[str]) -> list[str]:
    return [row["pathname"] for row in classify_hms_result_catalog(catalog) if row.get("result_class") == "loss"]


def find_hms_excess_precipitation_pathnames(catalog: dict[str, Any] | list[str]) -> list[str]:
    return [
        row["pathname"]
        for row in classify_hms_result_catalog(catalog)
        if row.get("result_class") == "excess_precipitation"
    ]


def load_hms_result_catalog(dss_path: str | Path) -> dict[str, Any]:
    catalog = catalog_dss_file(dss_path)
    classified = classify_hms_result_catalog(catalog)
    return {
        **catalog,
        "classified": classified,
        "pathname_count": len(classified),
        "flow_pathnames": find_hms_flow_pathnames(catalog),
        "flow_pathname_count": len(find_hms_flow_pathnames(catalog)),
    }


def _is_date_d_part(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}[A-Za-z]{3}\d{4}", value))


def _condensed_pathname(pathname: str) -> str:
    parts = _pathname_parts(pathname)
    if _is_date_d_part(parts[3]):
        parts[3] = ""
    return "/" + "/".join(parts) + "/"


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe.lower() or "hms_timeseries"


def build_hms_dss_read_script(
    dss_path: str | Path,
    pathnames: list[str],
    output_dir: str | Path,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    output = _resolve(output_dir)
    scripts = output / ".hydrolite_scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    script = scripts / "read_hms_result_timeseries.py"
    content = [
        "# -*- coding: ascii -*-",
        "from hec.heclib.dss import HecDss",
        "import math",
        f"dss_path = {_jython_unicode_literal(_resolve(dss_path))}",
        f"pathnames = {pathnames!r}",
        f"requested_start = {start!r}",
        f"requested_end = {end!r}",
        "dss = HecDss.open(dss_path)",
        "try:",
        "    for index, pathname in enumerate(pathnames):",
        "        try:",
        "            data = dss.get(pathname)",
        "            count = int(data.numberValues)",
        "            values = []",
        "            missing = 0",
        "            for raw in data.values:",
        "                value = float(raw)",
        "                if math.isnan(value) or value <= -1.0e30:",
        "                    values.append('')",
        "                    missing += 1",
        "                else:",
        "                    values.append(repr(value))",
        "            fields = [str(index), pathname, str(count), str(data.getStartTime().dateAndTime()), str(data.getEndTime().dateAndTime()), str(data.interval), str(data.units), str(data.type), str(missing)]",
        "            print 'HYDROLITE_HMS_TS_META|' + '|'.join(fields)",
        "            print 'HYDROLITE_HMS_TS_VALUES|' + str(index) + '|' + ','.join(values)",
        "        except Exception as exc:",
        "            print 'HYDROLITE_HMS_TS_ERROR|' + str(index) + '|' + pathname + '|' + str(exc).replace('\\n', ' ')",
        "finally:",
        "    dss.done()",
    ]
    script.write_text("\n".join(content) + "\n", encoding="ascii")
    return script


def _parse_hec_datetime(value: str) -> pd.Timestamp | None:
    match = re.fullmatch(r"\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4}),\s*(\d{1,2}):(\d{2})\s*", str(value))
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    hour_value = int(hour)
    base = pd.Timestamp(f"{day} {month} {year} {hour_value % 24:02d}:{minute}")
    return base + pd.Timedelta(days=1) if hour_value == 24 else base


def _parse_timeseries_markers(text: str, pathnames: list[str]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for line in text.splitlines():
        if line.startswith("HYDROLITE_HMS_TS_META|"):
            fields = line.split("|", 10)
            if len(fields) < 10:
                continue
            index = int(fields[1])
            result[index] = {
                "pathname": fields[2],
                "number_values": int(fields[3]),
                "start": fields[4],
                "end": fields[5],
                "interval": int(fields[6]),
                "units": fields[7],
                "type": fields[8],
                "missing_count": int(fields[9]),
                "read_status": "success",
                "errors": [],
                "warnings": [],
            }
        elif line.startswith("HYDROLITE_HMS_TS_VALUES|"):
            _, index_text, values_text = line.split("|", 2)
            index = int(index_text)
            values: list[float | None] = []
            for value in values_text.split(","):
                values.append(None if value == "" else float(value))
            result.setdefault(index, {"pathname": pathnames[index]})["values"] = values
        elif line.startswith("HYDROLITE_HMS_TS_ERROR|"):
            fields = line.split("|", 3)
            index = int(fields[1])
            result[index] = {
                "pathname": fields[2],
                "read_status": "failed",
                "errors": [fields[3] if len(fields) > 3 else "Unknown HEC-DSS read error."],
                "warnings": [],
                "values": [],
            }
    return result


def validate_hms_timeseries_read(result: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    values = result.get("values", [])
    if result.get("read_status") != "success":
        errors.extend(result.get("errors", ["Read status is not success."]))
    if result.get("number_values") != len(values):
        errors.append("DSS number_values does not match values length.")
    if result.get("interval", 0) <= 0:
        errors.append("DSS interval must be positive.")
    if _parse_hec_datetime(result.get("start", "")) is None:
        errors.append("DSS start time could not be parsed.")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def _cross_validate_result_window(hms_project_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    context_path = hms_project_dir / "reports" / "hec_hms_rainfall_context.json"
    if not context_path.is_file():
        return {"status": "unavailable", "warnings": ["Rainfall/control context is unavailable for result-window cross-check."]}
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
        expected_start = pd.Timestamp(context["start"])
        expected_end = pd.Timestamp(context["end"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "warnings": [f"Rainfall/control context could not be parsed: {exc}"]}
    comparable = [
        item for item in result.get("series", [])
        if item.get("read_status") == "success" and item.get("flow_semantics") == "instantaneous_flow"
    ]
    starts = [_parse_hec_datetime(item.get("start", "")) for item in comparable]
    ends = [_parse_hec_datetime(item.get("end", "")) for item in comparable]
    starts = [value for value in starts if value is not None]
    ends = [value for value in ends if value is not None]
    actual_start = min(starts) if starts else None
    actual_end = max(ends) if ends else None
    matches = actual_start == expected_start and actual_end == expected_end
    return {
        "status": "passed" if matches else "warning",
        "expected_start": expected_start.isoformat(),
        "expected_end": expected_end.isoformat(),
        "actual_start": actual_start.isoformat() if actual_start is not None else None,
        "actual_end": actual_end.isoformat() if actual_end is not None else None,
        "source": str(context_path),
        "warnings": [] if matches else ["Result flow time range differs from the rainfall/control context."],
    }


def read_hms_dss_timeseries(
    dss_path: str | Path,
    pathnames: list[str] | None = None,
    output_dir: str | Path | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    target = _resolve(dss_path)
    output = _resolve(output_dir or DEFAULT_RESULTS_DIR)
    timeseries_dir = output / "timeseries"
    timeseries_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_hms_result_catalog(target)
    requested = list(pathnames or catalog["flow_pathnames"])
    groups: dict[str, list[str]] = {}
    for pathname in requested:
        groups.setdefault(_condensed_pathname(pathname), []).append(pathname)
    condensed = list(groups)
    script = build_hms_dss_read_script(target, condensed, output)
    attempt = _run_hms_script(script, output, min(max(int(timeout), 1), 60))
    combined_text = f"{attempt.get('stdout', '')}\n{attempt.get('stderr', '')}"
    parsed = _parse_timeseries_markers(combined_text, condensed)
    series_results: list[dict[str, Any]] = []
    failed_pathnames: list[dict[str, str]] = []
    successful_source_pathnames = 0
    for index, pathname in enumerate(condensed):
        item = parsed.get(
            index,
            {
                "pathname": pathname,
                "read_status": "failed",
                "errors": ["HEC-DSS script returned no marker for this pathname."],
                "warnings": [],
                "values": [],
            },
        )
        source_pathnames = groups[pathname]
        item["source_pathnames"] = source_pathnames
        item["source_pathname_count"] = len(source_pathnames)
        item.update({key: value for key, value in parse_dss_pathname(pathname).items() if key not in item})
        validation = validate_hms_timeseries_read(item)
        item["validation"] = validation
        if validation["status"] == "passed":
            start_time = _parse_hec_datetime(item["start"])
            timestamps = pd.date_range(start_time, periods=item["number_values"], freq=f"{item['interval']}min")
            values = pd.Series(item["values"], dtype="Float64")
            frame = pd.DataFrame(
                {
                    "timestamp": timestamps,
                    "flow_original": values,
                    "original_unit": item.get("units", ""),
                    "pathname": pathname,
                    "element_id": item.get("element_name", ""),
                    "parameter": item.get("parameter", ""),
                    "source": "HEC-HMS 4.13 result DSS",
                    "scenario": item.get("run_name", ""),
                }
            )
            filename = _safe_filename(f"{item.get('element_name', 'element')}_{item.get('parameter', 'parameter')}") + ".csv"
            csv_path = timeseries_dir / filename
            frame.to_csv(csv_path, index=False, date_format="%Y-%m-%d %H:%M:%S")
            item["csv_path"] = str(csv_path)
            item["timestamp_method"] = "dss_start_plus_regular_interval"
            item["timestamps"] = [timestamp.isoformat() for timestamp in timestamps]
            successful_source_pathnames += len(source_pathnames)
        else:
            for source_pathname in source_pathnames:
                failed_pathnames.append({"pathname": source_pathname, "error": "; ".join(validation["errors"])})
        series_results.append(item)
    fatal = _fatal_hms_lines(combined_text)
    result = {
        "status": "success" if successful_source_pathnames and not failed_pathnames else ("partial" if successful_source_pathnames else "failed"),
        "backend": "hec_hms_java",
        "dss_path": str(target),
        "requested_pathname_count": len(requested),
        "unique_series_count": len(condensed),
        "successful_pathname_count": successful_source_pathnames,
        "failed_pathname_count": len(failed_pathnames),
        "failed_pathnames": failed_pathnames,
        "series": series_results,
        "script": str(script),
        "returncode": attempt.get("returncode"),
        "runtime_seconds": attempt.get("runtime_seconds", 0.0),
        "timed_out": attempt.get("timed_out", False),
        "process_cleanup_confirmed": attempt.get("process_terminated", False),
        "fatal_errors": fatal,
        "warnings": [] if not fatal else ["HEC-DSS process emitted fatal/error lines; inspect the manifest."],
    }
    return result


def write_hms_timeseries_catalog(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    catalog_rows = [{key: value for key, value in row.items() if key != "warnings"} | {"warnings": "; ".join(row.get("warnings", []))} for row in result.get("catalog", [])]
    dss_catalog_json = output / "dss_catalog.json"
    dss_catalog_xlsx = output / "dss_catalog.xlsx"
    flow_json = output / "flow_pathnames.json"
    flow_xlsx = output / "flow_pathnames.xlsx"
    manifest = output / "hms_timeseries_read_manifest.json"
    report = output / "hms_timeseries_read_report.md"
    dss_catalog_json.write_text(json.dumps(_json_safe(result.get("catalog", [])), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.DataFrame(catalog_rows).to_excel(dss_catalog_xlsx, index=False)
    flow_rows = [row for row in catalog_rows if row.get("flow_semantics") != "not_flow"]
    flow_json.write_text(json.dumps(_json_safe(flow_rows), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.DataFrame(flow_rows).to_excel(flow_xlsx, index=False)
    manifest_payload = {key: value for key, value in result.items() if key != "series"}
    manifest_payload["series"] = [
        {key: value for key, value in item.items() if key not in {"values", "timestamps"}}
        for item in result.get("series", [])
    ]
    manifest.write_text(json.dumps(_json_safe(manifest_payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report.write_text(
        "\n".join(
            [
                "# HEC-HMS DSS flow time-series read report",
                "",
                f"- Status: `{result.get('status', 'unknown')}`",
                f"- Backend: `{result.get('backend', 'unavailable')}`",
                f"- Catalog pathnames: `{len(result.get('catalog', []))}`",
                f"- Requested flow pathnames: `{result.get('requested_pathname_count', 0)}`",
                f"- Successfully read flow pathnames: `{result.get('successful_pathname_count', 0)}`",
                f"- Failed pathnames: `{result.get('failed_pathname_count', 0)}`",
                f"- Result/control time-window check: `{result.get('time_window_crosscheck', {}).get('status', 'unavailable')}`",
                "- Missing DSS values are retained as missing; they are not filled with zero.",
                "- Timestamps are derived from the DSS start time and regular interval, never from system time.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "dss_catalog_json": dss_catalog_json,
        "dss_catalog_xlsx": dss_catalog_xlsx,
        "flow_json": flow_json,
        "flow_xlsx": flow_xlsx,
        "manifest": manifest,
        "report": report,
    }


def _normalize_unit_name(unit: str) -> str:
    return str(unit or "").strip().upper().replace(" ", "")


def convert_flow_values(values: Any, source_unit: str, target_unit: str = "CMS") -> tuple[pd.Series, dict[str, Any]]:
    source = _normalize_unit_name(source_unit)
    target = _normalize_unit_name(target_unit)
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").astype("Float64")
    if source not in FLOW_UNIT_FACTORS_TO_CMS or target not in FLOW_UNIT_FACTORS_TO_CMS:
        return pd.Series([pd.NA] * len(numeric), dtype="Float64"), {
            "status": "unit_unresolved",
            "source_unit": source_unit,
            "target_unit": target_unit,
            "conversion_applied": False,
            "conversion_factor": None,
        }
    factor = FLOW_UNIT_FACTORS_TO_CMS[source] / FLOW_UNIT_FACTORS_TO_CMS[target]
    return numeric * factor, {
        "status": "passed",
        "source_unit": source_unit,
        "target_unit": target_unit,
        "conversion_applied": not math.isclose(factor, 1.0),
        "conversion_factor": factor,
    }


def normalize_hms_flow_units(timeseries: pd.DataFrame, target_unit: str = "CMS") -> pd.DataFrame:
    frame = timeseries.copy()
    if "flow_original" not in frame.columns:
        source_column = next((name for name in ("value", "flow", "flow_cms") if name in frame.columns), None)
        if source_column is None:
            raise ValueError("HEC-HMS time series requires flow_original or a recognized flow column.")
        frame["flow_original"] = pd.to_numeric(frame[source_column], errors="coerce")
    unit = str(frame["original_unit"].dropna().iloc[0]) if "original_unit" in frame and frame["original_unit"].notna().any() else ""
    converted, details = convert_flow_values(frame["flow_original"], unit, target_unit)
    frame["original_unit"] = unit
    frame["flow_cms"] = converted
    frame["conversion_applied"] = details["conversion_applied"]
    frame["conversion_factor"] = details["conversion_factor"]
    frame.attrs["unit_validation"] = details
    return frame


def validate_flow_units(timeseries: pd.DataFrame) -> dict[str, Any]:
    if "original_unit" not in timeseries.columns:
        return {"status": "unit_unresolved", "errors": ["original_unit column is missing."]}
    units = sorted(set(timeseries["original_unit"].dropna().astype(str)))
    unsupported = [unit for unit in units if _normalize_unit_name(unit) not in FLOW_UNIT_FACTORS_TO_CMS]
    status = "passed" if units and not unsupported else "unit_unresolved"
    return {
        "status": status,
        "original_units": units,
        "target_unit": "CMS",
        "unsupported_units": unsupported,
        "errors": [f"Unsupported or non-flow unit: {unit}" for unit in unsupported] + ([] if units else ["No flow unit was found."]),
    }


def _infer_source_project(hms_project_dir: Path) -> Path | None:
    context = hms_project_dir / "reports" / "hec_hms_rainfall_context.json"
    if context.is_file():
        try:
            source = Path(json.loads(context.read_text(encoding="utf-8")).get("source_project_dir", ""))
            if source.is_dir():
                return source.resolve()
        except (OSError, json.JSONDecodeError):
            pass
    return None


def load_hydrolite_topology(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    subbasin_path = root / "data" / "subbasins.csv"
    reach_path = root / "data" / "reaches.csv"
    subbasins = pd.read_csv(subbasin_path) if subbasin_path.is_file() else pd.DataFrame()
    reaches = pd.read_csv(reach_path) if reach_path.is_file() else pd.DataFrame()
    return {
        "project_dir": str(root),
        "subbasins": subbasins,
        "reaches": reaches,
        "subbasin_path": str(subbasin_path),
        "reach_path": str(reach_path),
        "warnings": [
            message
            for path, message in (
                (subbasin_path, "HydroLite subbasins.csv is missing."),
                (reach_path, "HydroLite reaches.csv is missing."),
            )
            if not path.is_file()
        ],
    }


def load_hms_element_mappings(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    subbasin_path = data_dir / "subbasin_mapping.csv"
    reach_path = data_dir / "reach_mapping.csv"
    source = _infer_source_project(root)
    mapping_source = "generated_mapping_csv"
    if not subbasin_path.is_file() and source and (source / "data" / "subbasins.csv").is_file():
        shutil.copy2(source / "data" / "subbasins.csv", subbasin_path)
        mapping_source = "recovered_from_hydrolite_source"
    if not reach_path.is_file() and source and (source / "data" / "reaches.csv").is_file():
        shutil.copy2(source / "data" / "reaches.csv", reach_path)
        mapping_source = "recovered_from_hydrolite_source"
    return {
        "project_dir": str(root),
        "source_project_dir": str(source or ""),
        "subbasins": pd.read_csv(subbasin_path) if subbasin_path.is_file() else pd.DataFrame(),
        "reaches": pd.read_csv(reach_path) if reach_path.is_file() else pd.DataFrame(),
        "subbasin_mapping_file": str(subbasin_path),
        "reach_mapping_file": str(reach_path),
        "mapping_source": mapping_source,
        "warnings": [] if subbasin_path.is_file() and reach_path.is_file() else ["One or more HMS/HydroLite mapping CSV files are unavailable."],
    }


def _basin_element_types(hms_project_dir: Path) -> dict[str, str]:
    basin_path = next(iter(sorted(hms_project_dir.glob("*.basin"))), None)
    if not basin_path:
        return {}
    parsed = parse_hms_basin_file(basin_path)
    return {
        block["name"]: block["block_type"].lower()
        for block in parsed["blocks"]
        if block["block_type"] in {"Subbasin", "Reach", "Junction", "Sink", "Source", "Reservoir", "Diversion"}
    }


def identify_hydrolite_outlet(project_dir: str | Path) -> dict[str, Any]:
    topology = load_hydrolite_topology(project_dir)
    reaches = topology["reaches"]
    if reaches.empty or "reach_id" not in reaches.columns:
        return {"status": "unresolved", "candidates": [], "warnings": ["HydroLite reach topology is unavailable."]}
    reach_ids = set(reaches["reach_id"].dropna().astype(str))
    downstream_column = next((name for name in ("downstream_reach_id", "downstream_id", "to_reach_id") if name in reaches.columns), None)
    candidates: list[dict[str, Any]] = []
    for row in reaches.to_dict(orient="records"):
        reach_id = str(row.get("reach_id", ""))
        downstream = row.get(downstream_column) if downstream_column else None
        downstream_text = "" if pd.isna(downstream) else str(downstream).strip()
        if not downstream_text or downstream_text not in reach_ids:
            candidates.append(
                {
                    "outlet_id": reach_id,
                    "downstream_reference": downstream_text,
                    "reason": "No downstream HydroLite reach was found; this is a terminal reach.",
                    "confidence": "high",
                }
            )
    status = "verified" if len(candidates) == 1 else ("multiple_outlets" if len(candidates) > 1 else "unresolved")
    return {"status": status, "candidates": candidates, "selected_outlet_id": candidates[0]["outlet_id"] if len(candidates) == 1 else None, "warnings": []}


def map_hms_results_to_hydrolite_elements(
    project_dir: str | Path,
    hms_catalog: dict[str, Any] | list[dict[str, Any]],
    hydrolite_project_dir: str | Path | None = None,
) -> dict[str, Any]:
    hms_root = _resolve(project_dir)
    mappings = load_hms_element_mappings(hms_root)
    hydro_root = _resolve(hydrolite_project_dir) if hydrolite_project_dir else _infer_source_project(hms_root)
    topology = load_hydrolite_topology(hydro_root) if hydro_root else {"subbasins": pd.DataFrame(), "reaches": pd.DataFrame(), "warnings": ["Source HydroLite project unavailable."]}
    subbasin_ids = set(topology["subbasins"].get("subbasin_id", pd.Series(dtype=str)).dropna().astype(str))
    reach_ids = set(topology["reaches"].get("reach_id", pd.Series(dtype=str)).dropna().astype(str))
    element_types = _basin_element_types(hms_root)
    outlet = identify_hydrolite_outlet(hydro_root) if hydro_root else {"selected_outlet_id": None}
    rows = hms_catalog.get("classified", []) if isinstance(hms_catalog, dict) else hms_catalog
    mapping_rows: list[dict[str, Any]] = []
    for item in rows:
        if item.get("flow_semantics") == "not_flow":
            continue
        element = str(item.get("element_name") or item.get("b_part") or "")
        element_type = element_types.get(element, "unknown")
        hydro_id: str | None = None
        source = "unmapped"
        confidence = "none"
        warnings: list[str] = []
        if element in subbasin_ids:
            hydro_id, source, confidence = element, mappings["mapping_source"], "high"
            element_type = "subbasin"
        elif element in reach_ids:
            hydro_id, source, confidence = element, mappings["mapping_source"], "high"
            element_type = "reach"
        elif element.lower() in {"outlet", "sink"} and outlet.get("selected_outlet_id"):
            hydro_id, source, confidence = outlet["selected_outlet_id"], "basin_terminal_element_to_hydrolite_terminal_reach", "high"
            element_type = element_types.get(element, "outlet")
        else:
            warnings.append(f"No HydroLite element mapping was found for HMS element {element!r}.")
        mapping_rows.append(
            {
                "hms_element": element,
                "hms_element_type": element_type,
                "hydrolite_element_id": hydro_id,
                "pathname": item.get("pathname", ""),
                "parameter": item.get("parameter", ""),
                "result_class": item.get("result_class", ""),
                "mapping_source": source,
                "confidence": confidence,
                "warnings": "; ".join(warnings),
            }
        )
    mapped = sum(bool(row["hydrolite_element_id"]) for row in mapping_rows)
    return {
        "status": "passed" if mapping_rows and mapped == len(mapping_rows) else ("partial" if mapped else "failed"),
        "rows": mapping_rows,
        "flow_pathname_count": len(mapping_rows),
        "mapped_count": mapped,
        "unmapped_count": len(mapping_rows) - mapped,
        "mapping_files": {
            "subbasin": mappings["subbasin_mapping_file"],
            "reach": mappings["reach_mapping_file"],
        },
        "warnings": mappings["warnings"] + topology.get("warnings", []),
    }


def validate_hms_hydrolite_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    rows = mapping.get("rows", [])
    errors = []
    if not rows:
        errors.append("No flow pathname mappings were produced.")
    if mapping.get("flow_pathname_count") != len(rows):
        errors.append("Mapping row count does not match flow pathname count.")
    return {
        "status": "passed" if not errors and mapping.get("unmapped_count", 0) == 0 else ("partial" if rows else "failed"),
        "errors": errors,
        "unmapped_count": mapping.get("unmapped_count", 0),
    }


def write_hms_hydrolite_mapping_report(output_dir: str | Path, mapping: dict[str, Any]) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "hms_hydrolite_mapping.json"
    xlsx_path = output / "hms_hydrolite_mapping.xlsx"
    md_path = output / "hms_hydrolite_mapping_report.md"
    json_path.write_text(json.dumps(_json_safe(mapping), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.DataFrame(mapping.get("rows", [])).to_excel(xlsx_path, index=False)
    md_path.write_text(
        "\n".join(
            [
                "# HEC-HMS to HydroLite element mapping",
                "",
                f"- Status: `{mapping.get('status', 'unknown')}`",
                f"- Flow pathname rows: `{mapping.get('flow_pathname_count', 0)}`",
                f"- Mapped: `{mapping.get('mapped_count', 0)}`",
                f"- Unmapped: `{mapping.get('unmapped_count', 0)}`",
                "- Outlet mappings use basin/reach topology; peak magnitude is never used to select an outlet.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "xlsx": xlsx_path, "markdown": md_path}


def identify_hms_outlet_candidates(
    project_dir: str | Path,
    mapping: dict[str, Any],
    catalog: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, Any]:
    root = _resolve(project_dir)
    basin_path = next(iter(sorted(root.glob("*.basin"))), None)
    if not basin_path:
        return {"status": "outlet_unresolved", "candidates": [], "warnings": ["HEC-HMS basin file is missing."]}
    parsed = parse_hms_basin_file(basin_path)
    rows = catalog.get("classified", []) if isinstance(catalog, dict) else catalog
    elements_with_flow = {row.get("element_name") for row in rows if row.get("flow_semantics") != "not_flow"}
    candidates: list[dict[str, Any]] = []
    for block in parsed["blocks"]:
        if block["block_type"] not in {"Sink", "Junction", "Reach", "Reservoir", "Diversion"}:
            continue
        downstream = block["property_map"].get("Downstream", [""])[0].strip()
        if downstream or block["name"] not in elements_with_flow:
            continue
        explicit = block["block_type"] == "Sink" or "outlet" in block["name"].lower()
        candidates.append(
            {
                "hms_element": block["name"],
                "hms_element_type": block["block_type"],
                "priority": "A" if explicit else "B",
                "reason": (
                    "Explicit terminal sink/outlet element in HEC-HMS basin topology."
                    if explicit
                    else "Terminal HEC-HMS element has no downstream element."
                ),
                "confidence": "high" if explicit else "medium",
                "available_flow_pathnames": [
                    row.get("pathname", "")
                    for row in rows
                    if row.get("element_name") == block["name"] and row.get("flow_semantics") != "not_flow"
                ],
            }
        )
    candidates.sort(key=lambda row: (row["priority"], row["hms_element"]))
    if len(candidates) == 1:
        status = "high_confidence" if candidates[0]["confidence"] == "high" else "candidate_only"
    elif len(candidates) > 1:
        status = "multiple_outlets"
    else:
        status = "outlet_unresolved"
    return {
        "status": status,
        "candidates": candidates,
        "selected_candidate": candidates[0] if len(candidates) == 1 else None,
        "selection_rule": "basin_topology_only",
        "warnings": [] if candidates else ["No topology-backed HMS outlet candidate was found."],
    }


def select_verified_outlet_series(
    project_dir: str | Path,
    hms_timeseries: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    catalog = {"classified": [parse_dss_pathname(pathname) for pathname in hms_timeseries.get("requested_pathnames", [])]}
    if not catalog["classified"]:
        catalog = {"classified": [parse_dss_pathname(pathname) for item in hms_timeseries.get("series", []) for pathname in item.get("source_pathnames", [])]}
    candidates = identify_hms_outlet_candidates(project_dir, mapping, catalog)
    if candidates["status"] == "multiple_outlets":
        return {**candidates, "outlet_selection_status": "multiple_outlets", "selected_series": None}
    selected = candidates.get("selected_candidate")
    if not selected:
        return {**candidates, "outlet_selection_status": "outlet_unresolved", "selected_series": None}
    element = selected["hms_element"]
    eligible = [
        item
        for item in hms_timeseries.get("series", [])
        if item.get("read_status") == "success"
        and item.get("element_name") == element
        and item.get("flow_semantics") == "instantaneous_flow"
    ]
    exact = [item for item in eligible if item.get("parameter", "").upper() in {"FLOW", "OUTFLOW"}]
    if len(exact) == 1:
        chosen = exact[0]
        status = "verified"
        reason = "Single topology-backed terminal outlet with one instantaneous FLOW/OUTFLOW series."
    elif len(exact) > 1:
        chosen = None
        status = "multiple_outlet_series"
        reason = "Multiple instantaneous FLOW/OUTFLOW series remain for the verified outlet."
    else:
        chosen = None
        status = "outlet_series_unresolved"
        reason = "No instantaneous FLOW/OUTFLOW series was found for the topology-backed outlet."
    return {
        **candidates,
        "outlet_selection_status": status,
        "selected_outlet": element if chosen else None,
        "selected_pathname": chosen.get("pathname") if chosen else None,
        "selected_series": chosen,
        "selection_reason": reason,
        "quantitative_comparison_allowed": status in {"verified", "high_confidence"},
    }


def write_outlet_selection_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "outlet_selection.json"
    md_path = output / "outlet_selection.md"
    xlsx_path = output / "outlet_candidates.xlsx"
    payload = {key: value for key, value in result.items() if key != "selected_series"}
    json_path.write_text(json.dumps(_json_safe(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.DataFrame(result.get("candidates", [])).to_excel(xlsx_path, index=False)
    md_path.write_text(
        "\n".join(
            [
                "# HEC-HMS outlet selection",
                "",
                f"- Status: `{result.get('outlet_selection_status', result.get('status', 'unknown'))}`",
                f"- Selected outlet: `{result.get('selected_outlet', 'unresolved')}`",
                f"- Selected pathname: `{result.get('selected_pathname', 'unresolved')}`",
                f"- Basis: {result.get('selection_reason', result.get('selection_rule', 'unavailable'))}",
                "- Outlet selection is topology-based. It does not select the series with the largest peak.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path, "xlsx": xlsx_path}


def discover_hydrolite_flow_outputs(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    names = {
        "result_flow.csv",
        "hydrolite_streamflow.csv",
        "outlet_hydrograph.csv",
        "outlet_flow_timeseries.csv",
        "reach_flow_timeseries.csv",
        "observed_vs_simulated.csv",
    }
    candidates: list[dict[str, Any]] = []
    search_roots = [root / "output", root / "reports", PROJECT_ROOT / "output" / root.name, PROJECT_ROOT / "output"]
    seen: set[Path] = set()
    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        for path in search_root.rglob("*.csv"):
            resolved = path.resolve()
            if resolved in seen or path.name not in names:
                continue
            seen.add(resolved)
            try:
                frame = pd.read_csv(path, nrows=5)
                columns = list(frame.columns)
            except Exception as exc:  # noqa: BLE001
                candidates.append({"path": str(resolved), "status": "unreadable", "columns": [], "error": str(exc)})
                continue
            time_column = next((name for name in ("timestamp", "datetime", "time") if name in columns), None)
            flow_columns = [name for name in columns if "flow" in name.lower()]
            candidates.append(
                {
                    "path": str(resolved),
                    "status": "candidate" if time_column and flow_columns else "unsupported_schema",
                    "time_column": time_column,
                    "flow_columns": flow_columns,
                    "columns": columns,
                }
            )
    viable = [row for row in candidates if row["status"] == "candidate"]
    viable.sort(
        key=lambda row: (
            0 if Path(row["path"]).is_relative_to(root) else 1,
            0 if Path(row["path"]).name == "result_flow.csv" and "outflow_cms" in row["flow_columns"] else 1,
            row["path"],
        )
    )
    return {
        "status": "found" if viable else "not_found",
        "project_dir": str(root),
        "candidates": candidates,
        "selected": viable[0] if viable else None,
        "warnings": [] if viable else ["No complete HydroLite flow time series was found."],
    }


def normalize_hydrolite_flow_timeseries(data: pd.DataFrame) -> pd.DataFrame:
    timestamp_column = next((name for name in ("timestamp", "datetime", "time") if name in data.columns), None)
    flow_column = next((name for name in ("flow_cms", "outflow_cms", "outlet_flow", "flow") if name in data.columns), None)
    if timestamp_column is None or flow_column is None:
        raise ValueError("HydroLite flow output requires a time column and an outlet flow column.")
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(data[timestamp_column], errors="coerce"),
            "flow_cms": pd.to_numeric(data[flow_column], errors="coerce"),
        }
    )
    if frame["timestamp"].isna().any():
        raise ValueError("HydroLite flow output contains unparseable timestamps.")
    if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("HydroLite flow timestamps must be unique and increasing.")
    frame["element_id"] = "outlet"
    frame["source"] = "HydroLite result_flow.csv"
    frame["scenario"] = ""
    frame["unit"] = "CMS"
    frame.attrs["source_flow_column"] = flow_column
    return frame


def load_hydrolite_outlet_timeseries(project_dir: str | Path, outlet_id: str | None = None) -> pd.DataFrame:
    discovery = discover_hydrolite_flow_outputs(project_dir)
    selected = discovery.get("selected")
    if not selected:
        raise FileNotFoundError("No HydroLite outlet time series was found.")
    path = Path(selected["path"])
    data = pd.read_csv(path)
    frame = normalize_hydrolite_flow_timeseries(data)
    if outlet_id:
        reach_column = next((name for name in data.columns if name == f"reach_{outlet_id}_outflow_cms"), None)
        if reach_column:
            frame["flow_cms"] = pd.to_numeric(data[reach_column], errors="coerce")
            frame["element_id"] = outlet_id
            frame.attrs["source_flow_column"] = reach_column
    frame["scenario"] = path.parent.name
    frame.attrs["source_path"] = str(path)
    return frame


def write_hydrolite_flow_discovery_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "hydrolite_flow_discovery.json"
    md_path = output / "hydrolite_flow_discovery.md"
    json_path.write_text(json.dumps(_json_safe(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    selected = result.get("selected") or {}
    md_path.write_text(
        "\n".join(
            [
                "# HydroLite flow discovery",
                "",
                f"- Status: `{result.get('status', 'unknown')}`",
                f"- Selected source: `{selected.get('path', 'unavailable')}`",
                f"- Time column: `{selected.get('time_column', 'unavailable')}`",
                f"- Flow columns: `{', '.join(selected.get('flow_columns', []))}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path}


def _median_interval_minutes(frame: pd.DataFrame) -> float | None:
    times = pd.to_datetime(frame["timestamp"], errors="coerce").dropna().sort_values()
    differences = times.diff().dropna().dt.total_seconds().div(60)
    return float(differences.median()) if not differences.empty else None


def determine_comparison_window(hms_series: pd.DataFrame, hydrolite_series: pd.DataFrame) -> dict[str, Any]:
    hms = pd.to_datetime(hms_series["timestamp"], errors="coerce").dropna()
    hydro = pd.to_datetime(hydrolite_series["timestamp"], errors="coerce").dropna()
    if hms.empty or hydro.empty:
        return {"status": "unavailable", "warnings": ["One or both time series are empty."]}
    start = max(hms.min(), hydro.min())
    end = min(hms.max(), hydro.max())
    return {
        "status": "passed" if start <= end else "no_overlap",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "hms_interval_minutes": _median_interval_minutes(hms_series),
        "hydrolite_interval_minutes": _median_interval_minutes(hydrolite_series),
        "timezone_assumption": "naive local/event time; both sources contain no timezone offset",
        "warnings": [] if start <= end else ["HEC-HMS and HydroLite series do not overlap."],
    }


def align_flow_timeseries(
    hms_series: pd.DataFrame,
    hydrolite_series: pd.DataFrame,
    method: str = "exact",
    max_tolerance: str | pd.Timedelta | None = None,
) -> dict[str, Any]:
    hms = hms_series[["timestamp", "flow_cms"]].copy().rename(columns={"flow_cms": "hms_flow_cms"})
    hydro = hydrolite_series[["timestamp", "flow_cms"]].copy().rename(columns={"flow_cms": "hydrolite_flow_cms"})
    hms["timestamp"] = pd.to_datetime(hms["timestamp"], errors="coerce")
    hydro["timestamp"] = pd.to_datetime(hydro["timestamp"], errors="coerce")
    hms = hms.dropna(subset=["timestamp"]).sort_values("timestamp")
    hydro = hydro.dropna(subset=["timestamp"]).sort_values("timestamp")
    window = determine_comparison_window(hms.rename(columns={"hms_flow_cms": "flow_cms"}), hydro.rename(columns={"hydrolite_flow_cms": "flow_cms"}))
    warnings = list(window.get("warnings", []))
    if method == "exact":
        aligned = hms.merge(hydro, on="timestamp", how="inner")
        matched_hms = set(aligned["timestamp"])
        matched_hydro = matched_hms
    elif method == "nearest":
        tolerance = pd.Timedelta(max_tolerance) if max_tolerance is not None else pd.Timedelta(minutes=min(filter(None, [window.get("hms_interval_minutes"), window.get("hydrolite_interval_minutes")])) / 2)
        aligned = pd.merge_asof(hms, hydro, on="timestamp", direction="nearest", tolerance=tolerance).dropna(subset=["hydrolite_flow_cms"])
        matched_hms = set(aligned["timestamp"])
        matched_hydro = set(
            hydro.loc[hydro["timestamp"].apply(lambda value: bool(((aligned["timestamp"] - value).abs() <= tolerance).any())), "timestamp"]
        )
        warnings.append(f"Nearest alignment used tolerance {tolerance}; no interpolation was applied.")
    elif method in {"resample_mean", "resample_instantaneous"}:
        intervals = [value for value in (window.get("hms_interval_minutes"), window.get("hydrolite_interval_minutes")) if value]
        if not intervals:
            raise ValueError("A common interval cannot be determined for resampling.")
        interval = int(max(intervals))
        aggregation = "mean" if method == "resample_mean" else "last"
        hms_r = getattr(hms.set_index("timestamp")["hms_flow_cms"].resample(f"{interval}min"), aggregation)().dropna()
        hydro_r = getattr(hydro.set_index("timestamp")["hydrolite_flow_cms"].resample(f"{interval}min"), aggregation)().dropna()
        aligned = pd.concat([hms_r, hydro_r], axis=1, join="inner").dropna().reset_index()
        matched_hms = set(aligned["timestamp"])
        matched_hydro = matched_hms
        warnings.append(f"{method} used a documented {interval}-minute interval; no interpolation was applied.")
    else:
        raise ValueError(f"Unsupported alignment method: {method}")
    aligned["residual_cms"] = aligned["hydrolite_flow_cms"] - aligned["hms_flow_cms"]
    result = {
        "status": "passed" if len(aligned) >= 2 else "insufficient_data",
        "method": method,
        "aligned": aligned,
        "original_hms_records": len(hms),
        "original_hydrolite_records": len(hydro),
        "aligned_records": len(aligned),
        "unmatched_hms": len(hms) - len(matched_hms),
        "unmatched_hydrolite": len(hydro) - len(matched_hydro),
        "start": aligned["timestamp"].min().isoformat() if not aligned.empty else None,
        "end": aligned["timestamp"].max().isoformat() if not aligned.empty else None,
        "hms_interval_minutes": window.get("hms_interval_minutes"),
        "hydrolite_interval_minutes": window.get("hydrolite_interval_minutes"),
        "timezone_assumption": window.get("timezone_assumption"),
        "warnings": warnings,
    }
    return result


def validate_flow_alignment(aligned: dict[str, Any]) -> dict[str, Any]:
    frame = aligned.get("aligned", pd.DataFrame())
    errors: list[str] = []
    if len(frame) < 2:
        errors.append("At least two aligned records are required.")
    if not frame.empty and frame["timestamp"].duplicated().any():
        errors.append("Aligned timestamps are not unique.")
    for column in ("hms_flow_cms", "hydrolite_flow_cms"):
        if column not in frame.columns:
            errors.append(f"Missing aligned column: {column}")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def write_alignment_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "alignment_report.json"
    md_path = output / "alignment_report.md"
    metadata = {key: value for key, value in result.items() if key != "aligned"}
    json_path.write_text(json.dumps(_json_safe(metadata), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text("\n".join(["# Flow alignment", ""] + [f"- {key}: `{value}`" for key, value in metadata.items() if key != "warnings"]) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def _chart_setup(title: str, ylabel: str) -> tuple[plt.Figure, plt.Axes]:
    figure, axis = plt.subplots(figsize=(10, 5.5))
    axis.set_title(title)
    axis.set_xlabel("Event time")
    axis.set_ylabel(ylabel)
    axis.grid(True, alpha=0.25)
    return figure, axis


def _save_chart(figure: plt.Figure, path: Path, source_note: str) -> Path:
    figure.text(0.01, 0.01, source_note, fontsize=8, color="#555555")
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(figure)
    return path


def plot_hms_flow_pathnames(timeseries_result: dict[str, Any], output_path: str | Path) -> Path | None:
    readable = [
        item
        for item in timeseries_result.get("series", [])
        if item.get("read_status") == "success" and item.get("flow_semantics") == "instantaneous_flow" and Path(item.get("csv_path", "")).is_file()
    ]
    if not readable:
        return None
    figure, axis = _chart_setup("HEC-HMS flow result pathnames", "Flow (original DSS units)")
    for item in readable[:20]:
        frame = pd.read_csv(item["csv_path"], parse_dates=["timestamp"])
        axis.plot(frame["timestamp"], pd.to_numeric(frame["flow_original"], errors="coerce"), label=f"{item['element_name']} {item['parameter']}", linewidth=1.2)
    axis.legend(fontsize=7, ncol=2)
    return _save_chart(figure, _resolve(output_path), "Source: HEC-HMS 4.13 result DSS; no interpolation or missing-value filling.")


def plot_outlet_hydrograph_comparison(aligned: pd.DataFrame, output_path: str | Path) -> Path | None:
    if len(aligned) < 2:
        return None
    figure, axis = _chart_setup("Outlet hydrograph comparison", "Flow (m3/s)")
    axis.plot(aligned["timestamp"], aligned["hms_flow_cms"], label="HEC-HMS", linewidth=2)
    axis.plot(aligned["timestamp"], aligned["hydrolite_flow_cms"], label="HydroLite", linewidth=2)
    axis.legend()
    return _save_chart(figure, _resolve(output_path), f"Sources: HEC-HMS DSS and HydroLite result_flow.csv; aligned window {aligned['timestamp'].min()} to {aligned['timestamp'].max()}.")


def _cumulative_volume(frame: pd.DataFrame, flow_column: str) -> pd.Series:
    times = pd.to_datetime(frame["timestamp"])
    values = pd.to_numeric(frame[flow_column], errors="coerce")
    cumulative = [0.0]
    for index in range(1, len(frame)):
        seconds = (times.iloc[index] - times.iloc[index - 1]).total_seconds()
        left, right = values.iloc[index - 1], values.iloc[index]
        cumulative.append(cumulative[-1] + ((left + right) / 2.0 * seconds if pd.notna(left) and pd.notna(right) else np.nan))
    return pd.Series(cumulative, index=frame.index, dtype=float)


def plot_cumulative_volume_comparison(aligned: pd.DataFrame, output_path: str | Path) -> Path | None:
    if len(aligned) < 2:
        return None
    figure, axis = _chart_setup("Cumulative outlet volume comparison", "Cumulative volume (m3)")
    axis.plot(aligned["timestamp"], _cumulative_volume(aligned, "hms_flow_cms"), label="HEC-HMS")
    axis.plot(aligned["timestamp"], _cumulative_volume(aligned, "hydrolite_flow_cms"), label="HydroLite")
    axis.legend()
    return _save_chart(figure, _resolve(output_path), f"Trapezoidal integration over exact aligned timestamps, {aligned['timestamp'].min()} to {aligned['timestamp'].max()}.")


def plot_peak_timing_comparison(hms_metrics: dict[str, Any], hydrolite_metrics: dict[str, Any], output_path: str | Path) -> Path | None:
    if hms_metrics.get("peak_flow_cms") is None or hydrolite_metrics.get("peak_flow_cms") is None:
        return None
    figure, axis = plt.subplots(figsize=(8, 5))
    labels = ["HEC-HMS", "HydroLite"]
    values = [hms_metrics["peak_flow_cms"], hydrolite_metrics["peak_flow_cms"]]
    bars = axis.bar(labels, values, color=["#3973ac", "#27865b"])
    axis.set_title("Peak flow and timing comparison")
    axis.set_ylabel("Peak flow (m3/s)")
    for bar, metrics in zip(bars, (hms_metrics, hydrolite_metrics)):
        axis.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(metrics.get("peak_time", "")), ha="center", va="bottom", fontsize=8, rotation=10)
    return _save_chart(figure, _resolve(output_path), "Peak labels show event timestamps; these are model outputs, not warning thresholds.")


def plot_flow_scatter(aligned: pd.DataFrame, output_path: str | Path) -> Path | None:
    clean = aligned.dropna(subset=["hms_flow_cms", "hydrolite_flow_cms"])
    if len(clean) < 2:
        return None
    figure, axis = plt.subplots(figsize=(6.5, 6))
    axis.scatter(clean["hms_flow_cms"], clean["hydrolite_flow_cms"], alpha=0.8)
    maximum = float(max(clean["hms_flow_cms"].max(), clean["hydrolite_flow_cms"].max()))
    axis.plot([0, maximum], [0, maximum], linestyle="--", color="#555555", label="1:1")
    axis.set_title("Aligned outlet flow scatter")
    axis.set_xlabel("HEC-HMS flow (m3/s)")
    axis.set_ylabel("HydroLite flow (m3/s)")
    axis.legend()
    axis.grid(True, alpha=0.25)
    return _save_chart(figure, _resolve(output_path), f"Exact aligned records: {len(clean)}; no interpolation.")


def plot_residual_timeseries(aligned: pd.DataFrame, output_path: str | Path) -> Path | None:
    if len(aligned) < 2:
        return None
    figure, axis = _chart_setup("HydroLite minus HEC-HMS outlet flow", "Residual (m3/s)")
    axis.axhline(0, color="#555555", linewidth=1)
    axis.plot(aligned["timestamp"], aligned["residual_cms"], color="#a23b3b", label="HydroLite - HEC-HMS")
    axis.legend()
    return _save_chart(figure, _resolve(output_path), f"Exact aligned window {aligned['timestamp'].min()} to {aligned['timestamp'].max()}.")


def run_hms_result_extraction(
    hms_project_dir: str | Path,
    output_dir: str | Path = DEFAULT_RESULTS_DIR,
) -> dict[str, Any]:
    hms_root = _resolve(hms_project_dir)
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    dss_path = hms_root / "hydrolite_run.dss"
    catalog = load_hms_result_catalog(dss_path)
    read_result = read_hms_dss_timeseries(dss_path, catalog["flow_pathnames"], output, timeout=60)
    read_result["catalog"] = catalog["classified"]
    read_result["requested_pathnames"] = catalog["flow_pathnames"]
    read_result["time_window_crosscheck"] = _cross_validate_result_window(hms_root, read_result)
    catalog_outputs = write_hms_timeseries_catalog(output, read_result)
    mapping = map_hms_results_to_hydrolite_elements(hms_root, catalog)
    mapping_outputs = write_hms_hydrolite_mapping_report(output, mapping)
    outlet = select_verified_outlet_series(hms_root, read_result, mapping)
    outlet_outputs = write_outlet_selection_report(output, outlet)
    hms_chart = plot_hms_flow_pathnames(read_result, output / "hms_flow_pathnames.png")
    status = "completed" if catalog.get("status") == "success" and read_result["status"] == "success" and outlet.get("outlet_selection_status") in {"verified", "high_confidence"} else "partial"
    result = {
        "status": status,
        "hms_project_dir": str(hms_root),
        "dss_path": str(dss_path),
        "catalog_status": catalog.get("status"),
        "pathname_count": catalog.get("pathname_count", 0),
        "flow_pathname_count": catalog.get("flow_pathname_count", 0),
        "read_result": read_result,
        "mapping": mapping,
        "outlet_selection": outlet,
        "outputs": {
            **{key: str(path) for key, path in catalog_outputs.items()},
            **{f"mapping_{key}": str(path) for key, path in mapping_outputs.items()},
            **{f"outlet_{key}": str(path) for key, path in outlet_outputs.items()},
            "hms_flow_pathnames_chart": str(hms_chart or ""),
        },
        "warnings": read_result.get("warnings", []) + mapping.get("warnings", []) + outlet.get("warnings", []),
    }
    return result


def _write_standard_hydrolite_outputs(project_dir: Path, source: pd.DataFrame) -> dict[str, Path]:
    output = project_dir / "output" / "hydrology"
    output.mkdir(parents=True, exist_ok=True)
    outlet_path = output / "outlet_flow_timeseries.csv"
    reach_path = output / "reach_flow_timeseries.csv"
    manifest_path = output / "hydrology_timeseries_manifest.json"
    source[["timestamp", "element_id", "flow_cms", "source", "scenario", "unit"]].to_csv(outlet_path, index=False, date_format="%Y-%m-%d %H:%M:%S")
    original_path = Path(source.attrs.get("source_path", ""))
    reach_rows: list[pd.DataFrame] = []
    if original_path.is_file():
        original = pd.read_csv(original_path)
        timestamp_column = next((name for name in ("timestamp", "datetime", "time") if name in original.columns), None)
        for column in original.columns:
            match = re.fullmatch(r"reach_(.+)_outflow_cms", column)
            if match and timestamp_column:
                reach_rows.append(
                    pd.DataFrame(
                        {
                            "timestamp": pd.to_datetime(original[timestamp_column], errors="coerce"),
                            "element_id": match.group(1),
                            "flow_cms": pd.to_numeric(original[column], errors="coerce"),
                            "source": "HydroLite result_flow.csv",
                            "scenario": original_path.parent.name,
                            "unit": "CMS",
                        }
                    )
                )
    pd.concat(reach_rows, ignore_index=True).to_csv(reach_path, index=False, date_format="%Y-%m-%d %H:%M:%S") if reach_rows else pd.DataFrame(columns=["timestamp", "element_id", "flow_cms", "source", "scenario", "unit"]).to_csv(reach_path, index=False)
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": _now(),
                "source": str(source.attrs.get("source_path", "")),
                "source_flow_column": source.attrs.get("source_flow_column", ""),
                "outlet_records": len(source),
                "outlet_file": str(outlet_path),
                "reach_file": str(reach_path),
                "algorithm_changed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"outlet": outlet_path, "reach": reach_path, "manifest": manifest_path}


def _flat_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metrics.items() if key != "thresholds"}


def _portable_path(value: str | Path) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def _threshold_rows(model: str, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"model": model, **row} for row in metrics.get("thresholds", [])]


def _comparison_output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "aligned_csv": output_dir / "aligned_outlet_timeseries.csv",
        "hms_csv": output_dir / "hec_hms_outlet_timeseries.csv",
        "hydrolite_csv": output_dir / "hydrolite_outlet_timeseries.csv",
        "event_metrics": output_dir / "event_metrics.xlsx",
        "metrics_xlsx": output_dir / "model_comparison_metrics.xlsx",
        "metrics_csv": output_dir / "model_comparison_metrics.csv",
        "manifest": output_dir / "comparison_manifest.json",
        "report": output_dir / "comparison_report.md",
        "bundle": output_dir / "hec_hms_comparison_bundle.zip",
    }


def _selected_hms_frame(selected_series: dict[str, Any]) -> pd.DataFrame:
    csv_path = Path(selected_series.get("csv_path", ""))
    if not csv_path.is_file():
        raise FileNotFoundError("The selected HEC-HMS outlet time-series CSV is unavailable.")
    frame = pd.read_csv(csv_path, parse_dates=["timestamp"])
    normalized = normalize_hms_flow_units(frame)
    normalized["element_id"] = selected_series.get("element_name", "")
    normalized["source"] = "HEC-HMS 4.13 result DSS"
    normalized["scenario"] = selected_series.get("run_name", "")
    normalized["unit"] = "CMS"
    return normalized


def _write_comparison_workbooks(
    output: Path,
    result: dict[str, Any],
    hms_metrics: dict[str, Any],
    hydro_metrics: dict[str, Any],
    comparison_metrics: dict[str, Any],
) -> None:
    paths = _comparison_output_paths(output)
    alignment = {key: value for key, value in result["alignment"].items() if key != "aligned"}
    summary = {
        "comparison_status": result["status"],
        "hms_project_dir": _portable_path(result["hms_project_dir"]),
        "hydrolite_project_dir": _portable_path(result["hydrolite_project_dir"]),
        "hms_outlet": result["outlet_selection"].get("selected_outlet"),
        "hms_outlet_pathname": result["outlet_selection"].get("selected_pathname"),
        "hydrolite_outlet": result["hydrolite_outlet"].get("selected_outlet_id"),
        "alignment_method": alignment.get("method"),
        "aligned_records": alignment.get("aligned_records"),
        "unit_status": result["unit_validation"].get("status"),
        "reference_model": "HEC-HMS",
        "compared_model": "HydroLite",
    }
    outlet_mapping = pd.DataFrame(
        [
            {
                "hms_element": result["outlet_selection"].get("selected_outlet"),
                "hms_pathname": result["outlet_selection"].get("selected_pathname"),
                "hydrolite_element_id": result["hydrolite_outlet"].get("selected_outlet_id"),
                "selection_status": result["outlet_selection"].get("outlet_selection_status"),
                "selection_basis": result["outlet_selection"].get("selection_reason"),
            }
        ]
    )
    warnings = pd.DataFrame({"warning": result.get("warnings", []) or ["None"]})
    comparison_row = {**comparison_metrics, **result["event_differences"]}
    comparison_row.pop("warnings", None)
    with pd.ExcelWriter(paths["event_metrics"], engine="openpyxl") as writer:
        pd.DataFrame([_flat_metrics(hms_metrics)]).to_excel(writer, sheet_name="hms_event_metrics", index=False)
        pd.DataFrame([_flat_metrics(hydro_metrics)]).to_excel(writer, sheet_name="hydrolite_event_metrics", index=False)
        pd.DataFrame(_threshold_rows("HEC-HMS", hms_metrics) + _threshold_rows("HydroLite", hydro_metrics)).to_excel(
            writer, sheet_name="threshold_diagnostics", index=False
        )
    with pd.ExcelWriter(paths["metrics_xlsx"], engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="summary", index=False)
        outlet_mapping.to_excel(writer, sheet_name="outlet_mapping", index=False)
        pd.DataFrame([_flat_metrics(hms_metrics)]).to_excel(writer, sheet_name="hms_event_metrics", index=False)
        pd.DataFrame([_flat_metrics(hydro_metrics)]).to_excel(writer, sheet_name="hydrolite_event_metrics", index=False)
        pd.DataFrame([comparison_row]).to_excel(writer, sheet_name="comparison_metrics", index=False)
        pd.DataFrame([alignment]).to_excel(writer, sheet_name="alignment", index=False)
        warnings.to_excel(writer, sheet_name="warnings", index=False)
    pd.DataFrame([comparison_row]).to_csv(paths["metrics_csv"], index=False)


def write_hms_comparison_report(output_dir: str | Path, result: dict[str, Any] | None = None) -> Path:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = _comparison_output_paths(output)
    if result is None:
        if not paths["manifest"].is_file():
            raise FileNotFoundError(f"Comparison manifest not found: {paths['manifest']}")
        result = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    hms = result.get("hms_event_metrics", {})
    hydro = result.get("hydrolite_event_metrics", {})
    metrics = result.get("comparison_metrics", {})
    differences = result.get("event_differences", {})
    alignment = result.get("alignment", {})
    warnings = result.get("warnings", [])
    lines = [
        "# HEC-HMS and HydroLite event comparison",
        "",
        f"- Comparison status: `{result.get('status', 'unknown')}`",
        f"- HEC-HMS outlet: `{result.get('outlet_selection', {}).get('selected_outlet', 'unresolved')}`",
        f"- Outlet selection status: `{result.get('outlet_selection', {}).get('outlet_selection_status', 'unresolved')}`",
        f"- Outlet selection basis: {result.get('outlet_selection', {}).get('selection_reason', 'unavailable')}",
        f"- HEC-HMS original unit: `{result.get('unit_validation', {}).get('original_units', [])}`",
        f"- Standard unit: `CMS`",
        f"- Alignment: `{alignment.get('method', 'unavailable')}`, records `{alignment.get('aligned_records', 0)}`",
        f"- Window: `{alignment.get('start', '')}` to `{alignment.get('end', '')}`",
        "- Statistical convention: HEC-HMS is the reference series and HydroLite is the compared series.",
        "- No interpolation or missing-value filling was used for the default exact comparison.",
        "",
        "## Event metrics",
        "",
        "| Metric | HEC-HMS | HydroLite |",
        "|---|---:|---:|",
        f"| Peak flow (m3/s) | {hms.get('peak_flow_cms')} | {hydro.get('peak_flow_cms')} |",
        f"| Peak time | {hms.get('peak_time')} | {hydro.get('peak_time')} |",
        f"| Runoff volume (m3) | {hms.get('runoff_volume_m3')} | {hydro.get('runoff_volume_m3')} |",
        f"| Centroid time | {hms.get('centroid_time')} | {hydro.get('centroid_time')} |",
        "",
        "## Model differences",
        "",
        f"- Peak-flow percent difference: `{differences.get('peak_flow_percent_difference')}`",
        f"- Peak timing difference (HydroLite - HEC-HMS, hr): `{differences.get('peak_timing_difference_hr')}`",
        f"- Runoff-volume percent difference: `{differences.get('runoff_volume_percent_difference')}`",
        f"- RMSE: `{metrics.get('RMSE')}`",
        f"- MAE: `{metrics.get('MAE')}`",
        f"- NSE: `{metrics.get('NSE')}`",
        f"- KGE: `{metrics.get('KGE')}`",
        f"- PBIAS: `{metrics.get('PBIAS')}`",
        f"- R2: `{metrics.get('R2')}`",
        "",
        "## Limitations",
        "",
        "This is a same-event model-output comparison. Neither model is thereby calibrated for a real project, and diagnostic relative thresholds are not statutory flood-warning levels.",
        "The HEC-HMS workflow stage remains partial; calibration and flood forecasting remain planned.",
    ]
    if warnings:
        lines.extend(["", "## Warnings", ""] + [f"- {warning}" for warning in warnings])
    paths["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths["report"]


def export_hms_comparison_bundle(output_dir: str | Path) -> Path:
    output = _resolve(output_dir)
    paths = _comparison_output_paths(output)
    candidates = [
        paths["aligned_csv"],
        paths["hms_csv"],
        paths["hydrolite_csv"],
        paths["event_metrics"],
        paths["metrics_xlsx"],
        paths["metrics_csv"],
        paths["report"],
        *sorted((output / "charts").glob("*.png")),
    ]
    forbidden = ("data_raw", "external", "secret", "credential", "checkpoint", ".dss", ".pt", ".pth", ".ckpt", ".onnx")
    with zipfile.ZipFile(paths["bundle"], "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(path for path in candidates if path.is_file()):
            relative = path.relative_to(output)
            lowered = relative.as_posix().lower()
            if any(token in lowered for token in forbidden) or path == paths["bundle"]:
                continue
            archive.write(path, arcname=relative.as_posix())
    return paths["bundle"]


def validate_hms_comparison_outputs(output_dir: str | Path) -> dict[str, Any]:
    output = _resolve(output_dir)
    paths = _comparison_output_paths(output)
    required = [
        paths["aligned_csv"], paths["hms_csv"], paths["hydrolite_csv"], paths["event_metrics"],
        paths["metrics_xlsx"], paths["metrics_csv"], paths["manifest"], paths["report"], paths["bundle"],
    ]
    missing = [str(path) for path in required if not path.is_file()]
    sheet_errors: list[str] = []
    if paths["metrics_xlsx"].is_file():
        required_sheets = {"summary", "outlet_mapping", "hms_event_metrics", "hydrolite_event_metrics", "comparison_metrics", "alignment", "warnings"}
        present = set(pd.ExcelFile(paths["metrics_xlsx"]).sheet_names)
        sheet_errors = sorted(required_sheets - present)
    bundle_errors: list[str] = []
    if paths["bundle"].is_file():
        with zipfile.ZipFile(paths["bundle"]) as archive:
            for name in archive.namelist():
                lowered = name.lower()
                if any(token in lowered for token in (".dss", "data_raw", "external", "secret", "credential", ".pt", ".pth", ".ckpt", ".onnx")):
                    bundle_errors.append(name)
    errors = [f"Missing output: {path}" for path in missing]
    errors += [f"Missing workbook sheet: {sheet}" for sheet in sheet_errors]
    errors += [f"Forbidden bundle member: {name}" for name in bundle_errors]
    return {"status": "passed" if not errors else "failed", "errors": errors, "output_dir": str(output)}


def run_hms_hydrolite_comparison(
    hms_project_dir: str | Path,
    hydrolite_project_dir: str | Path,
    output_dir: str | Path = DEFAULT_COMPARISON_DIR,
    outlet_id: str | None = None,
) -> dict[str, Any]:
    hms_root = _resolve(hms_project_dir)
    hydro_root = _resolve(hydrolite_project_dir)
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    extraction_dir = DEFAULT_RESULTS_DIR if output == DEFAULT_COMPARISON_DIR else output.parent / "hec_hms_results"
    extraction = run_hms_result_extraction(hms_root, extraction_dir)
    outlet = extraction["outlet_selection"]
    discovery = discover_hydrolite_flow_outputs(hydro_root)
    write_hydrolite_flow_discovery_report(output, discovery)
    hydro_outlet = identify_hydrolite_outlet(hydro_root)
    warnings = list(extraction.get("warnings", [])) + list(discovery.get("warnings", [])) + list(hydro_outlet.get("warnings", []))
    result: dict[str, Any] = {
        "status": "outlet_unresolved",
        "generated_at": _now(),
        "hms_project_dir": str(hms_root),
        "hydrolite_project_dir": str(hydro_root),
        "extraction_status": extraction["status"],
        "outlet_selection": {key: value for key, value in outlet.items() if key != "selected_series"},
        "hydrolite_outlet": hydro_outlet,
        "warnings": warnings,
    }
    if outlet.get("outlet_selection_status") not in {"verified", "high_confidence"}:
        result["warnings"].append("Quantitative comparison was blocked because the HEC-HMS outlet is not verified.")
        result["outputs"] = {key: str(path) for key, path in _comparison_output_paths(output).items()}
        Path(result["outputs"]["manifest"]).write_text(json.dumps(_json_safe(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_hms_comparison_report(output, result)
        return result
    hms_frame = _selected_hms_frame(outlet["selected_series"])
    unit_validation = validate_flow_units(hms_frame)
    result["unit_validation"] = unit_validation
    if unit_validation["status"] != "passed":
        result["status"] = "unit_unresolved"
        result["warnings"].extend(unit_validation["errors"])
        result["outputs"] = {key: str(path) for key, path in _comparison_output_paths(output).items()}
        Path(result["outputs"]["manifest"]).write_text(json.dumps(_json_safe(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_hms_comparison_report(output, result)
        return result
    selected_hydro_outlet = outlet_id or hydro_outlet.get("selected_outlet_id")
    hydro_frame = load_hydrolite_outlet_timeseries(hydro_root, selected_hydro_outlet)
    _write_standard_hydrolite_outputs(hydro_root, hydro_frame)
    alignment = align_flow_timeseries(hms_frame, hydro_frame, method="exact")
    alignment_validation = validate_flow_alignment(alignment)
    write_alignment_report(output, alignment)
    result["alignment"] = {key: value for key, value in alignment.items() if key != "aligned"}
    result["alignment_validation"] = alignment_validation
    if alignment_validation["status"] != "passed":
        result["status"] = "alignment_failed"
        result["warnings"].extend(alignment_validation["errors"])
        result["outputs"] = {key: str(path) for key, path in _comparison_output_paths(output).items()}
        Path(result["outputs"]["manifest"]).write_text(json.dumps(_json_safe(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_hms_comparison_report(output, result)
        return result
    aligned = alignment["aligned"]
    hms_aligned = aligned[["timestamp", "hms_flow_cms"]].rename(columns={"hms_flow_cms": "flow_cms"})
    hydro_aligned = aligned[["timestamp", "hydrolite_flow_cms"]].rename(columns={"hydrolite_flow_cms": "flow_cms"})
    hms_metrics = calculate_event_flow_metrics(hms_aligned)
    hydro_metrics = calculate_event_flow_metrics(hydro_aligned)
    metric_validation = {"hms": validate_event_metrics(hms_metrics), "hydrolite": validate_event_metrics(hydro_metrics)}
    comparison_metrics = calculate_all_metrics(aligned["hms_flow_cms"], aligned["hydrolite_flow_cms"])
    event_differences = compare_event_flow_metrics(hms_metrics, hydro_metrics)
    result.update(
        {
            "status": "completed",
            "hms_event_metrics": hms_metrics,
            "hydrolite_event_metrics": hydro_metrics,
            "event_metric_validation": metric_validation,
            "comparison_metrics": comparison_metrics,
            "event_differences": event_differences,
            "warnings": result["warnings"] + comparison_metrics.get("warnings", []),
        }
    )
    paths = _comparison_output_paths(output)
    hms_frame.to_csv(paths["hms_csv"], index=False, date_format="%Y-%m-%d %H:%M:%S")
    hydro_frame.to_csv(paths["hydrolite_csv"], index=False, date_format="%Y-%m-%d %H:%M:%S")
    aligned.to_csv(paths["aligned_csv"], index=False, date_format="%Y-%m-%d %H:%M:%S")
    charts_dir = output / "charts"
    charts = {
        "hms_flow_pathnames": plot_hms_flow_pathnames(extraction["read_result"], charts_dir / "hms_flow_pathnames.png"),
        "outlet_hydrograph_comparison": plot_outlet_hydrograph_comparison(aligned, charts_dir / "outlet_hydrograph_comparison.png"),
        "cumulative_volume_comparison": plot_cumulative_volume_comparison(aligned, charts_dir / "cumulative_volume_comparison.png"),
        "peak_timing_comparison": plot_peak_timing_comparison(hms_metrics, hydro_metrics, charts_dir / "peak_timing_comparison.png"),
        "flow_scatter": plot_flow_scatter(aligned, charts_dir / "flow_scatter.png"),
        "residual_timeseries": plot_residual_timeseries(aligned, charts_dir / "residual_timeseries.png"),
    }
    result["charts"] = {key: str(path or "") for key, path in charts.items()}
    _write_comparison_workbooks(output, result, hms_metrics, hydro_metrics, comparison_metrics)
    result["outputs"] = {key: str(path) for key, path in paths.items()}
    manifest_payload = {key: value for key, value in result.items() if key != "read_result"}
    paths["manifest"].write_text(json.dumps(_json_safe(manifest_payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_hms_comparison_report(output, result)
    export_hms_comparison_bundle(output)
    return result
