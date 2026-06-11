from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class ValidationOutputs:
    output_dir: Path
    xlsx: Path
    csv: Path
    report_md: Path


@dataclass(frozen=True)
class ValidationResult:
    outputs: ValidationOutputs
    checks: pd.DataFrame
    overview: pd.DataFrame
    errors: pd.DataFrame
    warnings: pd.DataFrame

    @property
    def has_fatal_errors(self) -> bool:
        return not self.errors.empty


CHECK_COLUMNS = ["case_file", "case_name", "check_group", "check_name", "status", "message", "severity"]
OVERVIEW_COLUMNS = ["case_file", "case_name", "validation_status", "fatal_error_count", "warning_count", "message"]


def discover_case_files(target: str | Path) -> list[Path]:
    path = Path(target).expanduser().resolve()
    if path.is_dir():
        return sorted([*path.glob("*.yaml"), *path.glob("*.yml")])
    return [path]


def _project_root_for_target(target: Path) -> Path:
    if target.is_dir() and target.name == "cases":
        return target.parent
    if target.is_file() and target.parent.name == "cases":
        return target.parent.parent
    return target if target.is_dir() else target.parent


def _base_dir(case_file: Path) -> Path:
    return case_file.parent.parent if case_file.parent.name == "cases" else case_file.parent


def _resolve(base: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _nested(mapping: dict[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _first(mapping: dict[str, Any], paths: list[tuple[str, ...]]) -> Any:
    for path in paths:
        value = _nested(mapping, *path)
        if value not in (None, ""):
            return value
    return None


def _add(
    rows: list[dict[str, Any]],
    case_file: Path,
    case_name: str,
    group: str,
    name: str,
    status: str,
    message: str,
    severity: str,
) -> None:
    rows.append(
        {
            "case_file": str(case_file),
            "case_name": case_name,
            "check_group": group,
            "check_name": name,
            "status": status,
            "message": message,
            "severity": severity,
        }
    )


def _column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    by_lower = {column.lower(): column for column in df.columns}
    for candidate in candidates:
        found = by_lower.get(candidate.lower())
        if found is not None:
            return found
    return None


def _read_yaml(case_file: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    case_name = case_file.stem
    if not case_file.exists():
        _add(rows, case_file, case_name, "yaml", "file_exists", "failed", f"YAML not found: {case_file}", "fatal")
        return {}
    try:
        with case_file.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except Exception as exc:
        _add(rows, case_file, case_name, "yaml", "parse", "failed", f"YAML parse failed: {exc}", "fatal")
        return {}
    if not isinstance(raw, dict):
        _add(rows, case_file, case_name, "yaml", "root_mapping", "failed", "YAML root must be a mapping.", "fatal")
        return {}
    _add(rows, case_file, str(raw.get("name", raw.get("case_name", case_name))), "yaml", "parse", "passed", "YAML parsed.", "info")
    return raw


def _case_paths(raw: dict[str, Any], base: Path) -> dict[str, Path | None]:
    input_dir_value = _first(raw, [("inputs", "directory"), ("input", "directory")])
    input_dir = _resolve(base, input_dir_value) if input_dir_value else base
    output_value = _first(raw, [("outputs", "directory"), ("output", "folder")])
    return {
        "rainfall": _resolve(
            input_dir,
            _first(raw, [("inputs", "rainfall"), ("input", "rainfall_csv")]) or "",
        )
        if _first(raw, [("inputs", "rainfall"), ("input", "rainfall_csv")])
        else None,
        "subbasin": _resolve(
            input_dir,
            _first(raw, [("inputs", "subcatchments"), ("input", "subbasin_csv")]) or "",
        )
        if _first(raw, [("inputs", "subcatchments"), ("input", "subbasin_csv")])
        else None,
        "reach": _resolve(
            input_dir,
            _first(raw, [("inputs", "reaches"), ("input", "reach_csv")]) or "",
        )
        if _first(raw, [("inputs", "reaches"), ("input", "reach_csv")])
        else None,
        "output": _resolve(base, output_value) if output_value else None,
    }


def _validate_yaml(case_file: Path, raw: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[str, float | None]:
    case_name = str(_first(raw, [("case_name",), ("name",)]) or case_file.stem)
    if _first(raw, [("case_name",), ("name",)]) is None:
        _add(rows, case_file, case_name, "yaml", "case_name", "failed", "Missing case_name/name.", "fatal")
    else:
        _add(rows, case_file, case_name, "yaml", "case_name", "passed", "Case name is configured.", "info")

    dt_minutes = _first(raw, [("time", "dt_minutes")])
    model_dt_hours = _first(raw, [("model", "time_step_hours")])
    dt_hours: float | None = None
    if dt_minutes not in (None, ""):
        try:
            dt_hours = float(dt_minutes) / 60.0
            if dt_hours <= 0:
                raise ValueError
            _add(rows, case_file, case_name, "yaml", "time.dt_minutes", "passed", "time.dt_minutes is positive.", "info")
        except Exception:
            _add(rows, case_file, case_name, "yaml", "time.dt_minutes", "failed", "time.dt_minutes must be > 0.", "fatal")
    elif model_dt_hours not in (None, ""):
        try:
            dt_hours = float(model_dt_hours)
            if dt_hours <= 0:
                raise ValueError
            _add(
                rows,
                case_file,
                case_name,
                "yaml",
                "time.dt_minutes",
                "passed",
                "Using existing model.time_step_hours as dt.",
                "info",
            )
        except Exception:
            _add(rows, case_file, case_name, "yaml", "time.dt_minutes", "failed", "model.time_step_hours must be > 0.", "fatal")
    else:
        _add(rows, case_file, case_name, "yaml", "time.dt_minutes", "failed", "Missing time.dt_minutes or model.time_step_hours.", "fatal")

    for check_name, path in [
        ("time.start", ("time", "start")),
        ("time.end", ("time", "end")),
    ]:
        if _nested(raw, *path) in (None, ""):
            _add(rows, case_file, case_name, "yaml", check_name, "warning", f"Missing {check_name}; current HydroLite infers time from rainfall CSV.", "warning")
        else:
            _add(rows, case_file, case_name, "yaml", check_name, "passed", f"{check_name} is configured.", "info")

    for check_name, paths in [
        ("input.rainfall_csv", [("input", "rainfall_csv"), ("inputs", "rainfall")]),
        ("input.subbasin_csv", [("input", "subbasin_csv"), ("inputs", "subcatchments")]),
        ("input.reach_csv", [("input", "reach_csv"), ("inputs", "reaches")]),
        ("output.folder", [("output", "folder"), ("outputs", "directory")]),
    ]:
        if _first(raw, paths) in (None, ""):
            _add(rows, case_file, case_name, "yaml", check_name, "failed", f"Missing {check_name}.", "fatal")
        else:
            _add(rows, case_file, case_name, "yaml", check_name, "passed", f"{check_name} is configured.", "info")

    for check_name, paths, fallback in [
        ("hydrology.method", [("hydrology", "method")], "SCS-CN"),
        ("routing.channel_method", [("routing", "channel_method")], "Muskingum"),
    ]:
        if _first(raw, paths) in (None, ""):
            _add(rows, case_file, case_name, "yaml", check_name, "warning", f"Missing {check_name}; using MVP default {fallback}.", "warning")
        else:
            _add(rows, case_file, case_name, "yaml", check_name, "passed", f"{check_name} is configured.", "info")

    output_dir = _case_paths(raw, _base_dir(case_file))["output"]
    if output_dir is not None:
        data_raw = (_base_dir(case_file) / "data_raw").resolve()
        try:
            output_dir.resolve().relative_to(data_raw)
            _add(rows, case_file, case_name, "yaml", "output.folder_writable", "failed", "Output folder must not be inside data_raw.", "fatal")
        except ValueError:
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                _add(rows, case_file, case_name, "yaml", "output.folder_writable", "passed", "Output folder exists or can be created.", "info")
            except Exception as exc:
                _add(rows, case_file, case_name, "yaml", "output.folder_writable", "failed", f"Output folder cannot be created: {exc}", "fatal")
    return case_name, dt_hours


def _validate_rainfall(case_file: Path, case_name: str, path: Path | None, rows: list[dict[str, Any]]) -> tuple[pd.DataFrame | None, str | None, str | None]:
    if path is None:
        _add(rows, case_file, case_name, "rainfall_csv", "file_exists", "failed", "rainfall_csv is not configured.", "fatal")
        return None, None, None
    if not path.exists():
        _add(rows, case_file, case_name, "rainfall_csv", "file_exists", "failed", f"Rainfall CSV not found: {path}", "fatal")
        return None, None, None
    _add(rows, case_file, case_name, "rainfall_csv", "file_exists", "passed", f"Found {path}.", "info")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        _add(rows, case_file, case_name, "rainfall_csv", "read", "failed", f"Cannot read rainfall CSV: {exc}", "fatal")
        return None, None, None
    time_col = _column(df, ["time", "datetime", "date"])
    rain_col = _column(df, ["rainfall", "rain_mm"])
    subbasin_col = _column(df, ["subbasin_id"])
    if time_col is None:
        _add(rows, case_file, case_name, "rainfall_csv", "time_column", "failed", "Missing time/datetime column.", "fatal")
    else:
        parsed = pd.to_datetime(df[time_col], errors="coerce")
        if parsed.isna().any():
            _add(rows, case_file, case_name, "rainfall_csv", "time_parse", "failed", f"Column {time_col} contains unparseable times.", "fatal")
        else:
            _add(rows, case_file, case_name, "rainfall_csv", "time_parse", "passed", f"Column {time_col} can be parsed.", "info")
    if rain_col is None:
        _add(rows, case_file, case_name, "rainfall_csv", "rainfall_column", "failed", "Missing rainfall/rain_mm column.", "fatal")
    else:
        rainfall = pd.to_numeric(df[rain_col], errors="coerce")
        if rainfall.isna().any() or (rainfall < 0).any():
            _add(rows, case_file, case_name, "rainfall_csv", "non_negative_rainfall", "failed", f"Column {rain_col} must be numeric and non-negative.", "fatal")
        else:
            _add(rows, case_file, case_name, "rainfall_csv", "non_negative_rainfall", "passed", "Rainfall values are non-negative.", "info")
    if subbasin_col is None:
        _add(rows, case_file, case_name, "rainfall_csv", "subbasin_id", "warning", "Missing subbasin_id; rainfall is treated as a global hyetograph for all subbasins.", "warning")
    elif df[subbasin_col].isna().any() or (df[subbasin_col].astype(str).str.strip() == "").any():
        _add(rows, case_file, case_name, "rainfall_csv", "subbasin_id_not_empty", "failed", "subbasin_id cannot be empty.", "fatal")
    else:
        _add(rows, case_file, case_name, "rainfall_csv", "subbasin_id_not_empty", "passed", "subbasin_id values are populated.", "info")
    return df, subbasin_col, rain_col


def _validate_subbasins(
    case_file: Path,
    case_name: str,
    path: Path | None,
    rainfall: pd.DataFrame | None,
    rainfall_subbasin_col: str | None,
    rows: list[dict[str, Any]],
) -> None:
    if path is None or not path.exists():
        _add(rows, case_file, case_name, "subbasin_csv", "file_exists", "failed", f"Subbasin CSV not found: {path}", "fatal")
        return
    _add(rows, case_file, case_name, "subbasin_csv", "file_exists", "passed", f"Found {path}.", "info")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        _add(rows, case_file, case_name, "subbasin_csv", "read", "failed", f"Cannot read subbasin CSV: {exc}", "fatal")
        return
    id_col = _column(df, ["subbasin_id", "id"])
    area_col = _column(df, ["area_km2"])
    cn_col = _column(df, ["cn", "curve_number"])
    lag_col = _column(df, ["lag_hours"])
    for label, column in [("subbasin_id", id_col), ("area_km2", area_col), ("cn", cn_col), ("lag_hours", lag_col)]:
        _add(rows, case_file, case_name, "subbasin_csv", f"{label}_column", "passed" if column else "failed", f"{label} column {'found' if column else 'missing'}.", "info" if column else "fatal")
    if area_col and (pd.to_numeric(df[area_col], errors="coerce") <= 0).any():
        _add(rows, case_file, case_name, "subbasin_csv", "area_km2_positive", "failed", "area_km2 must be > 0.", "fatal")
    elif area_col:
        _add(rows, case_file, case_name, "subbasin_csv", "area_km2_positive", "passed", "area_km2 values are positive.", "info")
    if cn_col:
        cn = pd.to_numeric(df[cn_col], errors="coerce")
        if cn.isna().any() or (cn <= 0).any() or (cn > 100).any():
            _add(rows, case_file, case_name, "subbasin_csv", "cn_range", "failed", "cn must satisfy 0 < cn <= 100.", "fatal")
        else:
            _add(rows, case_file, case_name, "subbasin_csv", "cn_range", "passed", "cn values are in range.", "info")
    if lag_col:
        lag = pd.to_numeric(df[lag_col], errors="coerce")
        if lag.isna().any() or (lag < 0).any():
            _add(rows, case_file, case_name, "subbasin_csv", "lag_hours_non_negative", "failed", "lag_hours must be >= 0.", "fatal")
        else:
            _add(rows, case_file, case_name, "subbasin_csv", "lag_hours_non_negative", "passed", "lag_hours values are non-negative.", "info")
    if rainfall is not None and rainfall_subbasin_col and id_col:
        missing = set(rainfall[rainfall_subbasin_col].astype(str)) - set(df[id_col].astype(str))
        if missing:
            _add(rows, case_file, case_name, "subbasin_csv", "rainfall_subbasin_match", "failed", f"rainfall subbasin_id not found: {sorted(missing)}", "fatal")
        else:
            _add(rows, case_file, case_name, "subbasin_csv", "rainfall_subbasin_match", "passed", "rainfall subbasin_id values match subbasins.", "info")


def _validate_reaches(case_file: Path, case_name: str, path: Path | None, dt_hours: float | None, rows: list[dict[str, Any]]) -> None:
    if path is None or not path.exists():
        _add(rows, case_file, case_name, "reach_csv", "file_exists", "failed", f"Reach CSV not found: {path}", "fatal")
        return
    _add(rows, case_file, case_name, "reach_csv", "file_exists", "passed", f"Found {path}.", "info")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        _add(rows, case_file, case_name, "reach_csv", "read", "failed", f"Cannot read reach CSV: {exc}", "fatal")
        return
    reach_col = _column(df, ["reach_id", "id"])
    k_col = _column(df, ["k_hours", "K_hours"])
    x_col = _column(df, ["x", "X"])
    for label, column in [("reach_id", reach_col), ("k_hours", k_col), ("x", x_col)]:
        _add(rows, case_file, case_name, "reach_csv", f"{label}_column", "passed" if column else "failed", f"{label} column {'found' if column else 'missing'}.", "info" if column else "fatal")
    if not (reach_col and k_col and x_col):
        return
    for _, row in df.iterrows():
        reach_id = str(row[reach_col])
        k = _to_float(row[k_col])
        x = _to_float(row[x_col])
        if k is None or k <= 0:
            _add(rows, case_file, case_name, "reach_csv", "k_hours_positive", "failed", f"reach_id={reach_id}, K={row[k_col]} must be > 0. Adjust dt, K or X.", "fatal")
            continue
        if x is None or x < 0 or x > 0.5:
            _add(rows, case_file, case_name, "reach_csv", "x_range", "failed", f"reach_id={reach_id}, X={row[x_col]} must satisfy 0 <= X <= 0.5. Adjust dt, K or X.", "fatal")
            continue
        _add(rows, case_file, case_name, "reach_csv", "muskingum_parameter_range", "passed", f"reach_id={reach_id}, K={k}, X={x} are in range.", "info")
        if dt_hours is not None:
            upper = 2 * k * (1 - x)
            lower = 2 * k * x
            if dt_hours > upper:
                _add(rows, case_file, case_name, "reach_csv", "muskingum_stability_upper", "failed", f"reach_id={reach_id}, dt={dt_hours}, K={k}, X={x} violates dt <= 2K(1-X). Adjust dt, K or X.", "fatal")
            elif dt_hours < lower:
                _add(rows, case_file, case_name, "reach_csv", "muskingum_stability_lower", "failed", f"reach_id={reach_id}, dt={dt_hours}, K={k}, X={x} violates dt >= 2KX. Adjust dt, K or X.", "fatal")
            else:
                _add(rows, case_file, case_name, "reach_csv", "muskingum_stability", "passed", f"reach_id={reach_id}, dt={dt_hours}, K={k}, X={x} satisfies stability conditions.", "info")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _validate_swmm(case_file: Path, case_name: str, raw: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    swmm = raw.get("swmm", {}) or {}
    if not isinstance(swmm, dict) or not swmm.get("enabled", False):
        _add(rows, case_file, case_name, "swmm", "enabled", "passed", "SWMM is not enabled.", "info")
        return
    inp_value = swmm.get("inp_file")
    if not inp_value:
        _add(rows, case_file, case_name, "swmm", "inp_file", "failed", "swmm.inp_file is required when SWMM is enabled.", "fatal")
    else:
        inp = _resolve(_base_dir(case_file), inp_value)
        if not inp.exists():
            _add(rows, case_file, case_name, "swmm", "inp_file_exists", "failed", f"SWMM inp_file not found: {inp}", "fatal")
        elif inp.suffix.lower() != ".inp":
            _add(rows, case_file, case_name, "swmm", "inp_file_suffix", "failed", f"SWMM inp_file must be .inp: {inp}", "fatal")
        else:
            _add(rows, case_file, case_name, "swmm", "inp_file", "passed", f"SWMM inp_file exists: {inp}", "info")
    coupling = swmm.get("coupling", {}) or {}
    if not isinstance(coupling, dict) or not coupling.get("enabled", False):
        return
    for key in ["target_node", "inflow_name", "flow_unit", "source_time_column", "source_flow_column"]:
        if not coupling.get(key):
            _add(rows, case_file, case_name, "swmm_coupling", key, "failed", f"swmm.coupling.{key} is required.", "fatal")
        else:
            _add(rows, case_file, case_name, "swmm_coupling", key, "passed", f"swmm.coupling.{key} is configured.", "info")
    source = coupling.get("source_flow_csv")
    if source:
        source_path = _resolve(_base_dir(case_file), source)
        if source_path.exists():
            try:
                df = pd.read_csv(source_path)
                missing = [column for column in [coupling.get("source_time_column"), coupling.get("source_flow_column")] if column and column not in df.columns]
                if missing:
                    _add(rows, case_file, case_name, "swmm_coupling", "source_flow_csv_columns", "failed", f"source_flow_csv missing columns: {missing}", "fatal")
                else:
                    _add(rows, case_file, case_name, "swmm_coupling", "source_flow_csv_columns", "passed", "source_flow_csv contains configured columns.", "info")
            except Exception as exc:
                _add(rows, case_file, case_name, "swmm_coupling", "source_flow_csv_read", "failed", f"Cannot read source_flow_csv: {exc}", "fatal")
        else:
            _add(rows, case_file, case_name, "swmm_coupling", "source_flow_csv_exists", "warning", f"source_flow_csv not found yet: {source_path}. It may be generated by the current run.", "warning")


def _validate_one(case_file: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw = _read_yaml(case_file, rows)
    if not raw:
        return rows
    case_name, dt_hours = _validate_yaml(case_file, raw, rows)
    paths = _case_paths(raw, _base_dir(case_file))
    rainfall, rainfall_subbasin_col, _rain_col = _validate_rainfall(case_file, case_name, paths["rainfall"], rows)
    _validate_subbasins(case_file, case_name, paths["subbasin"], rainfall, rainfall_subbasin_col, rows)
    _validate_reaches(case_file, case_name, paths["reach"], dt_hours, rows)
    _validate_swmm(case_file, case_name, raw, rows)
    return rows


def _build_overview(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty:
        return pd.DataFrame(columns=OVERVIEW_COLUMNS)
    rows = []
    for (case_file, case_name), group in checks.groupby(["case_file", "case_name"], dropna=False):
        fatal = group[group["severity"] == "fatal"]
        warnings = group[group["severity"] == "warning"]
        status = "failed" if not fatal.empty else ("warning" if not warnings.empty else "passed")
        message = "; ".join(fatal["message"].astype(str).head(3)) if not fatal.empty else "; ".join(warnings["message"].astype(str).head(3))
        rows.append(
            {
                "case_file": case_file,
                "case_name": case_name,
                "validation_status": status,
                "fatal_error_count": int(len(fatal)),
                "warning_count": int(len(warnings)),
                "message": message,
            }
        )
    return pd.DataFrame(rows, columns=OVERVIEW_COLUMNS)


def _write_report(path: Path, overview: pd.DataFrame, errors: pd.DataFrame, warnings: pd.DataFrame) -> None:
    def table(df: pd.DataFrame, columns: list[str]) -> str:
        if df.empty:
            return ""
        usable = [column for column in columns if column in df.columns]
        header = "| " + " | ".join(usable) + " |"
        separator = "| " + " | ".join("---" for _ in usable) + " |"
        body = []
        for _, row in df[usable].iterrows():
            body.append("| " + " | ".join("" if pd.isna(row[column]) else str(row[column]) for column in usable) + " |")
        return "\n".join([header, separator, *body])

    lines = [
        "# HydroLite-Mac Validation Report",
        "",
        "## Overview",
        "",
        table(overview, OVERVIEW_COLUMNS) if not overview.empty else "No cases found.",
        "",
        "## Errors",
        "",
        table(errors, CHECK_COLUMNS) if not errors.empty else "No fatal errors.",
        "",
        "## Warnings",
        "",
        table(warnings, CHECK_COLUMNS) if not warnings.empty else "No warnings.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def validate_target(target: str | Path) -> ValidationResult:
    target_path = Path(target).expanduser().resolve()
    project_root = _project_root_for_target(target_path)
    validation_dir = project_root / "output" / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    outputs = ValidationOutputs(
        output_dir=validation_dir,
        xlsx=validation_dir / "validation_summary.xlsx",
        csv=validation_dir / "validation_summary.csv",
        report_md=validation_dir / "validation_report.md",
    )

    all_rows: list[dict[str, Any]] = []
    case_files = discover_case_files(target_path)
    if not case_files:
        all_rows.append(
            {
                "case_file": str(target_path),
                "case_name": "",
                "check_group": "target",
                "check_name": "case_files",
                "status": "failed",
                "message": f"No .yaml or .yml files found: {target_path}",
                "severity": "fatal",
            }
        )
    for case_file in case_files:
        all_rows.extend(_validate_one(case_file))

    checks = pd.DataFrame(all_rows, columns=CHECK_COLUMNS)
    overview = _build_overview(checks)
    errors = checks[checks["severity"] == "fatal"].copy()
    warnings = checks[checks["severity"] == "warning"].copy()

    with pd.ExcelWriter(outputs.xlsx) as writer:
        overview.to_excel(writer, sheet_name="overview", index=False)
        checks.to_excel(writer, sheet_name="checks", index=False)
        errors.to_excel(writer, sheet_name="errors", index=False)
        warnings.to_excel(writer, sheet_name="warnings", index=False)
    checks.to_csv(outputs.csv, index=False)
    _write_report(outputs.report_md, overview, errors, warnings)
    return ValidationResult(outputs=outputs, checks=checks, overview=overview, errors=errors, warnings=warnings)
