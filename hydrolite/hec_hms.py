from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any
import zipfile

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAGNOSIS_DIR = PROJECT_ROOT / "output" / "hec_hms"
DEFAULT_HMS_PROJECT_DIR = PROJECT_ROOT / "output" / "hec_hms_project"
HMS_PROJECT_NAME = "HydroLite_HMS_Project"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        value = str(path)
        if value not in seen:
            seen.add(value)
            result.append(path)
    return result


def detect_hec_hms_installations() -> list[dict[str, Any]]:
    home = Path.home()
    candidates = [
        Path("/Applications/HEC-HMS.app"),
        *Path("/Applications").glob("HEC-HMS*.app"),
        home / "Applications" / "HEC-HMS.app",
        Path("/opt/hec-hms"),
        Path("/usr/local/hec-hms"),
        home / "HEC-HMS",
        Path("C:/Program Files/HEC/HEC-HMS"),
        Path("C:/Program Files (x86)/HEC/HEC-HMS"),
    ]
    if Path("/Applications/HEC").exists():
        candidates.extend(Path("/Applications/HEC").glob("HEC-HMS*"))
    if (home / "Applications").exists():
        candidates.extend((home / "Applications").glob("HEC-HMS*.app"))
    return [
        {
            "path": str(path),
            "exists": path.exists(),
            "kind": "app" if path.suffix.lower() == ".app" else "directory",
            "platform_hint": "windows" if str(path).startswith("C:") else platform.system().lower(),
        }
        for path in _unique_paths(candidates)
    ]


def detect_hec_hms_executables() -> list[dict[str, Any]]:
    candidates: list[tuple[Path, str]] = []
    for command in ("hec-hms", "hms", "HEC-HMS", "HMS"):
        located = shutil.which(command)
        if located:
            candidates.append((Path(located), f"PATH:{command}"))
    for installation in detect_hec_hms_installations():
        root = Path(installation["path"])
        for relative in (
            "Contents/MacOS/HEC-HMS",
            "Contents/MacOS/hec-hms",
            "Contents/MacOS/HMS",
            "Contents/MacOS/hms",
            "hec-hms.sh",
            "hms.sh",
            "bin/hec-hms.sh",
            "bin/hms.sh",
            "hec-hms.exe",
            "hms.exe",
            "bin/hec-hms.exe",
            "bin/hms.exe",
        ):
            candidates.append((root / relative, f"installation:{root}"))
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for path, source in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "path": key,
                "source": source,
                "exists": path.exists(),
                "executable": path.is_file() and os.access(path, os.X_OK),
            }
        )
    return rows


def _first_hec_hms_executable() -> str | None:
    for row in detect_hec_hms_executables():
        if row["exists"] and row["executable"]:
            return row["path"]
    return None


def hec_hms_version(candidate: str | Path | None = None) -> dict[str, Any]:
    executable = str(_resolve(candidate)) if candidate else _first_hec_hms_executable()
    if not executable:
        return {
            "status": "unavailable",
            "candidate": None,
            "stdout": "",
            "stderr": "No executable HEC-HMS command was detected.",
            "returncode": None,
            "attempts": [],
        }
    executable_path = Path(executable)
    app_root = next((parent for parent in executable_path.parents if parent.suffix.lower() == ".app"), None)
    if app_root:
        info_plist = app_root / "Contents" / "Info.plist"
        try:
            info = plistlib.loads(info_plist.read_bytes())
            version = str(info.get("CFBundleShortVersionString") or info.get("CFBundleVersion") or "unknown")
            return {
                "status": "available",
                "candidate": executable,
                "stdout": f"HEC-HMS {version}",
                "stderr": "",
                "returncode": 0,
                "attempts": [],
                "verification_method": "app_info_plist",
                "command_line_status": "unverified",
                "info_plist": str(info_plist),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "candidate": executable,
                "stdout": "",
                "stderr": f"Unable to read HEC-HMS app metadata safely: {exc}",
                "returncode": None,
                "attempts": [],
                "verification_method": "app_info_plist",
                "command_line_status": "unverified",
            }
    attempts: list[dict[str, Any]] = []
    for flag in ("--version", "-version", "-v", None):
        command = [executable] + ([flag] if flag else [])
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=5)
            attempt = {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
            attempts.append(attempt)
            output = attempt["stdout"] or attempt["stderr"]
            if completed.returncode == 0 and output:
                return {
                    "status": "available",
                    "candidate": executable,
                    "stdout": attempt["stdout"],
                    "stderr": attempt["stderr"],
                    "returncode": completed.returncode,
                    "attempts": attempts,
                    "verification_method": "command_line",
                    "command_line_status": "available",
                }
        except subprocess.TimeoutExpired:
            attempts.append({"command": command, "returncode": None, "stdout": "", "stderr": "Timed out after 5 seconds."})
        except Exception as exc:  # noqa: BLE001
            attempts.append({"command": command, "returncode": None, "stdout": "", "stderr": str(exc)})
    last = attempts[-1]
    return {
        "status": "failed",
        "candidate": executable,
        "stdout": last["stdout"],
        "stderr": last["stderr"] or "HEC-HMS did not return a usable version response.",
        "returncode": last["returncode"],
        "attempts": attempts,
        "verification_method": "command_line",
        "command_line_status": "failed",
    }


def _java_status() -> dict[str, Any]:
    candidates: list[tuple[Path, str]] = []
    system_java = shutil.which("java")
    if system_java:
        candidates.append((Path(system_java), "system_path"))
    for installation in detect_hec_hms_installations():
        root = Path(installation["path"])
        candidates.append((root / "Contents" / "Resources" / "jre" / "Contents" / "Home" / "bin" / "java", "hec_hms_bundled"))
    attempts = []
    seen: set[str] = set()
    for java, source in candidates:
        if str(java) in seen or not java.is_file() or not os.access(java, os.X_OK):
            continue
        seen.add(str(java))
        try:
            completed = subprocess.run([str(java), "-version"], capture_output=True, text=True, check=False, timeout=10)
            text = (completed.stderr or completed.stdout).strip()
            attempts.append({"path": str(java), "source": source, "returncode": completed.returncode, "output": text})
            if completed.returncode == 0 and text:
                return {
                    "available": True,
                    "path": str(java),
                    "source": source,
                    "returncode": completed.returncode,
                    "version": text,
                    "error": "",
                    "attempts": attempts,
                }
        except Exception as exc:  # noqa: BLE001
            attempts.append({"path": str(java), "source": source, "returncode": None, "output": str(exc)})
    return {
        "available": False,
        "path": system_java,
        "source": "system_path" if system_java else "none",
        "returncode": None,
        "version": "",
        "error": "No usable system or HEC-HMS bundled Java runtime was detected.",
        "attempts": attempts,
    }


def build_hec_hms_diagnosis() -> dict[str, Any]:
    installations = detect_hec_hms_installations()
    executables = detect_hec_hms_executables()
    installation_found = any(row["exists"] for row in installations)
    executable_found = any(row["exists"] and row["executable"] for row in executables)
    java = _java_status()
    version = hec_hms_version()
    warnings: list[str] = []
    if not installation_found:
        warnings.append("No HEC-HMS installation was detected in PATH or common platform locations.")
    if not executable_found:
        warnings.append("No executable hec-hms/hms command was detected; real HEC-HMS runs are unavailable.")
    if not java["available"]:
        warnings.append("Java Runtime is unavailable or unusable; HEC-HMS generally requires a compatible Java runtime.")
    if executable_found and version.get("command_line_status") == "available":
        recommendation = "command_line_available"
    elif installation_found or not executable_found:
        recommendation = "project_generation_only"
    else:
        recommendation = "unavailable"
    return {
        "status": "available" if installation_found else "unavailable",
        "generated_at": _now(),
        "operating_system": platform.platform(),
        "machine": platform.machine(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "working_directory": str(Path.cwd()),
        "java": java,
        "installations": installations,
        "executables": executables,
        "installation_detected": installation_found,
        "executable_detected": executable_found,
        "version_check": version,
        "recommended_integration": recommendation,
        "warnings": warnings,
        "next_steps": [
            "Generate and review the HEC-HMS project skeleton in this MVP.",
            "Open generated basin/met/control/run files in HEC-HMS for manual verification when HEC-HMS is available.",
            "Add verified command-line execution and DSS result reading in a later phase.",
        ],
    }


def write_hec_hms_diagnosis(output_dir: str | Path = "output/hec_hms") -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    diagnosis = build_hec_hms_diagnosis()
    json_path = output / "hec_hms_diagnosis.json"
    md_path = output / "hec_hms_diagnosis.md"
    json_path.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# HEC-HMS Backend Diagnosis",
        "",
        "> This is an environment and project-generation MVP. It does not claim verified HEC-HMS simulation capability.",
        "",
        f"- Operating system: `{diagnosis['operating_system']}`",
        f"- Python: `{diagnosis['python_executable']}`",
        f"- Java available: `{diagnosis['java']['available']}`",
        f"- HEC-HMS installation detected: `{diagnosis['installation_detected']}`",
        f"- HEC-HMS executable detected: `{diagnosis['executable_detected']}`",
        f"- Version status: `{diagnosis['version_check']['status']}`",
        f"- Version output: `{diagnosis['version_check']['stdout'] or diagnosis['version_check']['stderr']}`",
        f"- Recommended integration: `{diagnosis['recommended_integration']}`",
        "",
        "## Installation Candidates",
        "",
        "| Path | Exists | Kind |",
        "| --- | --- | --- |",
    ]
    for row in diagnosis["installations"]:
        lines.append(f"| {row['path']} | {row['exists']} | {row['kind']} |")
    lines.extend(["", "## Executable Candidates", "", "| Path | Exists | Executable | Source |", "| --- | --- | --- | --- |"])
    for row in diagnosis["executables"]:
        lines.append(f"| {row['path']} | {row['exists']} | {row['executable']} | {row['source']} |")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {message}" for message in diagnosis["warnings"])
    lines.extend(["", "## Next Steps", ""])
    lines.extend(f"- {message}" for message in diagnosis["next_steps"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"md": md_path, "json": json_path}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def collect_hydrolite_project_for_hms(project_dir: str | Path) -> dict[str, Any]:
    project = _resolve(project_dir)
    if not project.exists():
        raise FileNotFoundError(f"HydroLite project not found: {project}")
    project_yaml_path = project / "project.yaml"
    if not project_yaml_path.exists():
        raise FileNotFoundError(f"project.yaml not found: {project_yaml_path}")
    project_yaml = yaml.safe_load(project_yaml_path.read_text(encoding="utf-8")) or {}
    case_paths = sorted((project / "cases").glob("*.yaml")) + sorted((project / "cases").glob("*.yml"))
    cases = []
    for path in case_paths:
        try:
            cases.append({"path": str(path), "config": yaml.safe_load(path.read_text(encoding="utf-8")) or {}})
        except Exception as exc:  # noqa: BLE001
            cases.append({"path": str(path), "config": {}, "error": str(exc)})
    data_dir = project / "data"
    files = {
        "project_yaml": project_yaml_path,
        "subbasins": data_dir / "subbasins.csv",
        "reaches": data_dir / "reaches.csv",
        "rainfall": data_dir / "rainfall.csv",
        "basin_boundary": data_dir / "basin_boundary.geojson",
        "qgis_summary": project / "reports" / "qgis_project_summary.md",
    }
    warnings = []
    for key in ("subbasins", "reaches", "rainfall"):
        if not files[key].exists():
            warnings.append(f"Required project data for HMS mapping is missing: {files[key]}")
    existing_results = [
        str(path)
        for root_name in ("output", "reports")
        for path in (project / root_name).rglob("*")
        if path.is_file()
    ]
    return {
        "project_dir": str(project),
        "project_yaml": project_yaml,
        "cases": cases,
        "subbasins": _read_csv(files["subbasins"]),
        "reaches": _read_csv(files["reaches"]),
        "rainfall": _read_csv(files["rainfall"]),
        "input_files": {key: str(path) for key, path in files.items() if path.exists()},
        "existing_results": existing_results,
        "warnings": warnings,
    }


def generate_hms_project_structure(project_dir: str | Path, output_dir: str | Path) -> dict[str, Path]:
    output = _resolve(output_dir)
    directories = {name: output / name for name in ("basin", "met", "control", "run", "data", "scripts", "reports")}
    output.mkdir(parents=True, exist_ok=True)
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    project_file = output / f"{HMS_PROJECT_NAME}.hms"
    project_file.write_text(
        "\n".join(
            [
                f"Project: {HMS_PROJECT_NAME}",
                "     Description: Generated by HydroLite Studio HEC-HMS project generator MVP",
                "     Status: project_generation_mvp",
                "     Runnable Status: unverified",
                "     Basin: basin/hydrolite_basin.basin",
                "     Meteorologic Model: met/hydrolite_meteorologic.met",
                "     Control Specifications: control/hydrolite_control.control",
                "     Run: run/hydrolite_run.run",
                "End:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"root": output, "project_file": project_file, **directories}


def _value(row: pd.Series, names: tuple[str, ...], default: Any = "") -> Any:
    for name in names:
        if name in row.index and pd.notna(row[name]):
            return row[name]
    return default


def generate_hms_basin_model(project_data: dict[str, Any], output_dir: str | Path) -> Path:
    output = _resolve(output_dir) / "basin" / "hydrolite_basin.basin"
    lines = [
        "Basin: hydrolite_basin",
        "     Description: HydroLite mapped basin model; manual HEC-HMS review required",
        "     Status: project_generation_mvp",
        "     Runnable Status: unverified",
    ]
    for _, row in project_data["subbasins"].iterrows():
        subbasin_id = str(_value(row, ("subbasin_id", "id"), "SUBBASIN"))
        lag = float(_value(row, ("lag_time_hr", "lag_hours"), 1.0))
        lines.extend(
            [
                "",
                f"Subbasin: {subbasin_id}",
                f"     Area: {_value(row, ('area_km2',), 0)} KM2",
                "     Loss Method: SCS Curve Number",
                f"     Curve Number: {_value(row, ('cn',), 75)}",
                "     Transform Method: SCS Unit Hydrograph",
                f"     Lag: {lag * 60:.3f} MIN",
                f"     Outlet Reach: {_value(row, ('outlet_reach_id',), '')}",
            ]
        )
    for _, row in project_data["reaches"].iterrows():
        reach_id = str(_value(row, ("reach_id", "id"), "REACH"))
        lines.extend(
            [
                "",
                f"Reach: {reach_id}",
                "     Routing Method: Muskingum",
                f"     Length: {_value(row, ('length_km',), 0)} KM",
                f"     Slope: {_value(row, ('slope',), 0)}",
                f"     Muskingum K: {_value(row, ('muskingum_k_hr', 'k_hours'), 1.0)} HR",
                f"     Muskingum X: {_value(row, ('muskingum_x', 'x'), 0.2)}",
                f"     Upstream: {_value(row, ('upstream_reach_id',), '')}",
                f"     Downstream: {_value(row, ('downstream_reach_id',), '')}",
            ]
        )
    lines.extend(["", "End:"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _normalized_rainfall(project_data: dict[str, Any]) -> pd.DataFrame:
    source = project_data["rainfall"].copy()
    time_column = next((name for name in ("datetime", "time", "timestamp") if name in source.columns), None)
    rain_column = next((name for name in ("rainfall_mm", "rain_mm", "rainfall") if name in source.columns), None)
    if time_column is None or rain_column is None:
        return pd.DataFrame(columns=["datetime", "precipitation_mm"])
    return pd.DataFrame(
        {
            "datetime": pd.to_datetime(source[time_column], errors="coerce"),
            "precipitation_mm": pd.to_numeric(source[rain_column], errors="coerce"),
        }
    ).dropna(subset=["datetime", "precipitation_mm"])


def generate_hms_meteorologic_model(project_data: dict[str, Any], output_dir: str | Path) -> Path:
    root = _resolve(output_dir)
    rainfall = _normalized_rainfall(project_data)
    rainfall_path = root / "data" / "rainfall_timeseries.csv"
    rainfall.to_csv(rainfall_path, index=False, date_format="%Y-%m-%d %H:%M:%S")
    output = root / "met" / "hydrolite_meteorologic.met"
    output.write_text(
        "\n".join(
            [
                "Meteorologic Model: hydrolite_meteorologic",
                "     Description: Simple precipitation input mapping generated by HydroLite Studio",
                "     Status: project_generation_mvp",
                "     Runnable Status: unverified",
                "     Precipitation Method: Specified Hyetograph Mapping",
                "     Source File: ../data/rainfall_timeseries.csv",
                "     Units: MM",
                "End:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def _control_period(project_data: dict[str, Any]) -> tuple[pd.Timestamp, pd.Timestamp, int, list[str]]:
    rainfall = _normalized_rainfall(project_data)
    warnings: list[str] = []
    if rainfall.empty:
        start = pd.Timestamp("2026-01-01 00:00:00")
        end = start + pd.Timedelta(hours=24)
        warnings.append("Rainfall time range unavailable; used a 24-hour demo control period.")
        return start, end, 60, warnings
    times = rainfall["datetime"].sort_values()
    differences = times.diff().dropna().dt.total_seconds().div(60)
    dt_minutes = max(1, int(round(float(differences.median())))) if not differences.empty else 60
    if differences.empty:
        warnings.append("Only one rainfall timestamp was available; used a 60-minute control interval.")
    return times.min(), times.max(), dt_minutes, warnings


def generate_hms_control_specifications(project_data: dict[str, Any], output_dir: str | Path) -> Path:
    start, end, dt_minutes, warnings = _control_period(project_data)
    project_data.setdefault("warnings", []).extend(warnings)
    output = _resolve(output_dir) / "control" / "hydrolite_control.control"
    output.write_text(
        "\n".join(
            [
                "Control: hydrolite_control",
                "     Status: project_generation_mvp",
                "     Runnable Status: unverified",
                f"     Start Date: {start:%d %B %Y}",
                f"     Start Time: {start:%H:%M}",
                f"     End Date: {end:%d %B %Y}",
                f"     End Time: {end:%H:%M}",
                f"     Time Interval: {dt_minutes} MIN",
                "End:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def generate_hms_run_file(project_data: dict[str, Any], output_dir: str | Path) -> Path:
    output = _resolve(output_dir) / "run" / "hydrolite_run.run"
    output.write_text(
        "\n".join(
            [
                "Run: hydrolite_run",
                "     Description: HydroLite generated simulation run; manual verification required",
                "     Status: project_generation_mvp",
                "     Runnable Status: unverified",
                "     Basin: hydrolite_basin",
                "     Meteorologic Model: hydrolite_meteorologic",
                "     Control: hydrolite_control",
                "End:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def generate_hms_mapping_tables(project_data: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    root = _resolve(output_dir)
    subbasins = project_data["subbasins"].copy()
    reaches = project_data["reaches"].copy()
    subbasin_mapping = root / "data" / "subbasin_mapping.csv"
    reach_mapping = root / "data" / "reach_mapping.csv"
    subbasins.to_csv(subbasin_mapping, index=False)
    reaches.to_csv(reach_mapping, index=False)
    rainfall = root / "data" / "rainfall_timeseries.csv"
    if not rainfall.exists():
        _normalized_rainfall(project_data).to_csv(rainfall, index=False)
    workbook = root / "reports" / "hec_hms_mapping_summary.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        subbasins.to_excel(writer, sheet_name="subbasin_mapping", index=False)
        reaches.to_excel(writer, sheet_name="reach_mapping", index=False)
        _normalized_rainfall(project_data).to_excel(writer, sheet_name="rainfall_mapping", index=False)
        pd.DataFrame(
            [
                {"mapping": "subbasins", "count": len(subbasins)},
                {"mapping": "reaches", "count": len(reaches)},
                {"mapping": "rainfall_points", "count": len(_normalized_rainfall(project_data))},
            ]
        ).to_excel(writer, sheet_name="summary", index=False)
    return {
        "rainfall_timeseries": rainfall,
        "subbasin_mapping": subbasin_mapping,
        "reach_mapping": reach_mapping,
        "mapping_summary": workbook,
    }


def generate_hms_run_script(hms_project_dir: str | Path, output_dir: str | Path) -> dict[str, Path]:
    project = _resolve(hms_project_dir)
    scripts = _resolve(output_dir) / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shell = scripts / "run_hms_stub.sh"
    batch = scripts / "run_hms_stub.bat"
    shell.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "set -eu",
                f"HMS_PROJECT='{project / (HMS_PROJECT_NAME + '.hms')}'",
                "echo \"HEC-HMS execution is intentionally disabled in this MVP.\"",
                "echo \"Review the project first: $HMS_PROJECT\"",
                "echo \"Set a verified HEC-HMS executable and command syntax in a later integration phase.\"",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    shell.chmod(0o755)
    batch.write_text(
        "\n".join(
            [
                "@echo off",
                "echo HEC-HMS execution is intentionally disabled in this MVP.",
                f"echo Review the project first: {project / (HMS_PROJECT_NAME + '.hms')}",
                "echo Configure a verified HEC-HMS executable in a later integration phase.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"shell": shell, "batch": batch}


def validate_hms_project(hms_project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    expected = [
        f"{HMS_PROJECT_NAME}.hms",
        "basin/hydrolite_basin.basin",
        "met/hydrolite_meteorologic.met",
        "control/hydrolite_control.control",
        "run/hydrolite_run.run",
        "data/rainfall_timeseries.csv",
        "data/subbasin_mapping.csv",
        "data/reach_mapping.csv",
        "scripts/run_hms_stub.sh",
        "scripts/run_hms_stub.bat",
        "reports/hec_hms_project_report.md",
        "reports/hec_hms_project_manifest.json",
        "reports/hec_hms_mapping_summary.xlsx",
    ]
    checks = [{"file": name, "path": str(root / name), "exists": (root / name).is_file()} for name in expected]
    missing = [row["file"] for row in checks if not row["exists"]]
    return {
        "status": "passed" if not missing else "failed",
        "hms_project_dir": str(root),
        "checks": checks,
        "missing": missing,
        "runnable_status": "unverified",
        "warnings": ["The generated project skeleton requires manual HEC-HMS GUI or command-line review."],
    }


def write_hms_project_report(hms_project_dir: str | Path, result: dict[str, Any]) -> Path:
    root = _resolve(hms_project_dir)
    report = root / "reports" / "hec_hms_project_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    validation = result.get("validation", {})
    diagnosis = result.get("diagnosis_summary", {})
    lines = [
        "# HydroLite HEC-HMS Project Generator MVP",
        "",
        "> 该项目骨架需要在 HEC-HMS GUI 或命令行中人工复核。当前不代表真实 HMS 模拟已经验证。",
        "",
        f"- Status: `{result.get('status', 'project_generation_mvp')}`",
        f"- Runnable status: `{result.get('runnable_status', 'unverified')}`",
        f"- Source project: `{result.get('source_project_dir', '')}`",
        f"- HMS project directory: `{root}`",
        f"- Validation: `{validation.get('status', 'pending')}`",
        f"- HEC-HMS detected: `{diagnosis.get('installation_detected', False)}`",
        f"- Executable detected: `{diagnosis.get('executable_detected', False)}`",
        f"- Recommended integration: `{diagnosis.get('recommended_integration', 'project_generation_only')}`",
        "",
        "## Generated Structure",
        "",
        f"- `{HMS_PROJECT_NAME}.hms`: project index skeleton.",
        "- `basin/hydrolite_basin.basin`: subbasin and reach mappings.",
        "- `met/hydrolite_meteorologic.met`: simple precipitation input mapping.",
        "- `control/hydrolite_control.control`: inferred start/end and interval.",
        "- `run/hydrolite_run.run`: basin/met/control run association.",
        "- `data/`: normalized rainfall and mapping tables.",
        "- `scripts/`: non-executing command stubs.",
        "",
        "## Mapping Counts",
        "",
    ]
    for name, count in result.get("mapping_counts", {}).items():
        lines.append(f"- {name}: `{count}`")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in result.get("warnings", []))
    lines.extend(
        [
            "",
            "## Manual Review",
            "",
            "1. Open the generated project in a compatible HEC-HMS version.",
            "2. Verify basin connectivity, element coordinates, loss/transform/routing methods, units, and parameter ranges.",
            "3. Import or map precipitation using an HEC-HMS-supported time-series store if required.",
            "4. Verify control dates and the simulation interval.",
            "5. Do not use the run stubs for production until command syntax and DSS outputs are verified.",
        ]
    )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def create_hms_project_from_hydrolite(
    project_dir: str | Path,
    output_dir: str | Path = "output/hec_hms_project",
) -> dict[str, Any]:
    project_data = collect_hydrolite_project_for_hms(project_dir)
    structure = generate_hms_project_structure(project_dir, output_dir)
    root = structure["root"]
    generated = {
        "project_file": structure["project_file"],
        "basin_model": generate_hms_basin_model(project_data, root),
        "meteorologic_model": generate_hms_meteorologic_model(project_data, root),
        "control_specifications": generate_hms_control_specifications(project_data, root),
        "run_file": generate_hms_run_file(project_data, root),
    }
    generated.update(generate_hms_mapping_tables(project_data, root))
    scripts = generate_hms_run_script(root, root)
    generated.update({"run_script_sh": scripts["shell"], "run_script_bat": scripts["batch"]})
    diagnosis = build_hec_hms_diagnosis()
    result: dict[str, Any] = {
        "status": "project_generation_mvp",
        "runnable_status": "unverified",
        "source_project_dir": project_data["project_dir"],
        "hms_project_dir": str(root),
        "generated_at": _now(),
        "input_files": project_data["input_files"],
        "generated_files": {name: str(path) for name, path in generated.items()},
        "mapping_counts": {
            "subbasins": int(len(project_data["subbasins"])),
            "reaches": int(len(project_data["reaches"])),
            "rainfall_points": int(len(_normalized_rainfall(project_data))),
        },
        "warnings": list(dict.fromkeys(project_data["warnings"] + diagnosis["warnings"] + [
            "Generated HEC-HMS file syntax and project run behavior remain unverified.",
            "The project skeleton requires manual review in HEC-HMS before engineering use.",
        ])),
        "diagnosis_summary": {
            "installation_detected": diagnosis["installation_detected"],
            "executable_detected": diagnosis["executable_detected"],
            "version_status": diagnosis["version_check"]["status"],
            "recommended_integration": diagnosis["recommended_integration"],
        },
    }
    manifest = root / "reports" / "hec_hms_project_manifest.json"
    report = root / "reports" / "hec_hms_project_report.md"
    result["generated_files"]["manifest"] = str(manifest)
    result["generated_files"]["project_report"] = str(report)
    result["validation"] = {"status": "pending", "runnable_status": "unverified"}
    write_hms_project_report(root, result)
    manifest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result["validation"] = validate_hms_project(root)
    write_hms_project_report(root, result)
    manifest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def _app_root_for_executable(executable: str | Path) -> Path | None:
    path = _resolve(executable)
    return next((parent for parent in path.parents if parent.suffix.lower() == ".app"), None)


def _hms_main_class_flags(executable: str | Path) -> dict[str, Any]:
    app_root = _app_root_for_executable(executable)
    jar_path = app_root / "Contents" / "Resources" / "hms.jar" if app_root else None
    tokens = ("-script", "-debug", "-disableprint", "-info", "-lite", "--help", "-help", "--version", "-version")
    detected = {token: False for token in tokens}
    error = ""
    if jar_path and jar_path.is_file():
        try:
            with zipfile.ZipFile(jar_path) as archive:
                class_bytes = archive.read("hms/Hms.class")
            detected = {token: token.encode("ascii") in class_bytes for token in tokens}
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
    else:
        error = "hms.jar was not found next to the detected executable."
    return {"hms_jar": str(jar_path) if jar_path else "", "flags": detected, "error": error}


def _run_process_group(command: list[str], cwd: Path, timeout: int, environment: dict[str, str] | None = None) -> dict[str, Any]:
    timeout_seconds = max(1, min(int(timeout), 120))
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env={**os.environ, **(environment or {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            return {
                "status": "completed" if process.returncode == 0 else "failed",
                "pid": process.pid,
                "returncode": process.returncode,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "timed_out": False,
                "process_terminated": process.poll() is not None,
                "timeout_seconds": timeout_seconds,
            }
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.terminate()
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except OSError:
                    pass
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        pass
                stdout, stderr = process.communicate()
            return {
                "status": "timeout",
                "pid": process.pid,
                "returncode": process.returncode,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "timed_out": True,
                "process_terminated": process.poll() is not None,
                "timeout_seconds": timeout_seconds,
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "timed_out": False,
            "timeout_seconds": timeout_seconds,
        }


def _hms_script_runtime(executable: str | Path, script_path: str | Path) -> dict[str, Any]:
    launcher = str(_resolve(executable))
    app_root = _app_root_for_executable(launcher)
    if app_root:
        resources = app_root / "Contents" / "Resources"
        frameworks = app_root / "Contents" / "Frameworks"
        java = resources / "jre" / "Contents" / "Home" / "bin" / "java"
        if java.is_file() and os.access(java, os.X_OK):
            classpath = f"{resources}/*{os.pathsep}{resources / 'lib'}/*"
            args = [
                "-DMapPanel.NoVolatileImage=true",
                "-Xms32M",
                "-Dpython.path=",
                "-Dpython.home=.",
                f"-Djava.library.path={frameworks}",
                "-classpath",
                classpath,
                "hms.Hms",
                "-script",
                str(_resolve(script_path)),
            ]
            return {
                "executable": str(java),
                "launcher": launcher,
                "args": args,
                "cwd": str(resources),
                "environment": {
                    "DYLD_FALLBACK_LIBRARY_PATH": str(frameworks),
                    "GDAL_DATA": str(resources / "bin" / "gdal-data"),
                    "PROJ_LIB": str(resources / "bin" / "projlib"),
                },
                "mode": "bundled_java_script",
                "confidence": "medium",
            }
    return {
        "executable": launcher,
        "launcher": launcher,
        "args": ["-script", str(_resolve(script_path))],
        "cwd": str(Path(launcher).parent),
        "environment": {},
        "mode": "launcher_script",
        "confidence": "low",
    }


def run_hms_probe(candidate: str | Path | None = None, timeout: int = 30) -> dict[str, Any]:
    executable = str(_resolve(candidate)) if candidate else _first_hec_hms_executable()
    if not executable or not Path(executable).is_file():
        return {
            "status": "unavailable",
            "runnable_status": "unavailable",
            "executable": executable or "",
            "returncode": None,
            "stdout": "",
            "stderr": "No executable HEC-HMS candidate was found.",
            "timed_out": False,
            "simulation_attempted": False,
        }
    static_flags = _hms_main_class_flags(executable)
    if not static_flags["flags"].get("-script"):
        return {
            "status": "unavailable",
            "runnable_status": "unavailable",
            "executable": executable,
            "returncode": None,
            "stdout": "",
            "stderr": "The detected executable has no static -script capability evidence.",
            "timed_out": False,
            "simulation_attempted": False,
            "static_detection": static_flags,
        }
    probe_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydrolite_hms_probe_", delete=False, encoding="utf-8") as handle:
            probe_path = handle.name
            handle.write('print "HYDROLITE_HMS_PROBE_OK"\n')
        runtime = _hms_script_runtime(executable, probe_path)
        command = [runtime["executable"], *runtime["args"]]
        attempt = _run_process_group(command, Path(runtime["cwd"]), timeout, runtime["environment"])
        marker_found = "HYDROLITE_HMS_PROBE_OK" in f"{attempt['stdout']}\n{attempt['stderr']}"
        if marker_found and attempt["returncode"] == 0:
            status = "completed_probe"
            runnable_status = "completed_probe"
        elif attempt["timed_out"]:
            status = "probe_timeout"
            runnable_status = "probe"
        else:
            status = "failed"
            runnable_status = "failed"
        return {
            **attempt,
            "status": status,
            "runnable_status": runnable_status,
            "executable": executable,
            "command": command,
            "mode": runtime["mode"],
            "launcher": executable,
            "marker_found": marker_found,
            "simulation_attempted": False,
            "static_detection": static_flags,
        }
    finally:
        if probe_path:
            Path(probe_path).unlink(missing_ok=True)


def detect_hms_cli_modes(candidate: str | Path | None = None) -> dict[str, Any]:
    executable = str(_resolve(candidate)) if candidate else _first_hec_hms_executable()
    all_executables = detect_hec_hms_executables()
    macos_candidates: list[dict[str, Any]] = []
    script_candidates: list[dict[str, Any]] = []
    for installation in detect_hec_hms_installations():
        root = Path(installation["path"])
        macos_dir = root / "Contents" / "MacOS"
        if macos_dir.is_dir():
            for path in sorted(macos_dir.iterdir()):
                if path.is_file():
                    macos_candidates.append(
                        {"path": str(path), "executable": os.access(path, os.X_OK), "file_size_bytes": path.stat().st_size}
                    )
        for relative in ("hms.sh", "hec-hms.sh", "bin/hms.sh", "bin/hec-hms.sh"):
            path = root / relative
            script_candidates.append({"path": str(path), "exists": path.is_file(), "executable": os.access(path, os.X_OK)})
    static = _hms_main_class_flags(executable) if executable else {"hms_jar": "", "flags": {}, "error": "No executable."}
    flags = static.get("flags", {})
    probe = run_hms_probe(executable, timeout=10) if executable and flags.get("-script") else {
        "status": "unavailable",
        "runnable_status": "unavailable",
        "simulation_attempted": False,
        "stderr": "Script mode was not detected.",
    }
    return {
        "status": "partial" if executable else "unavailable",
        "executable": executable or "",
        "all_executable_candidates": all_executables,
        "macos_contents_executables": macos_candidates,
        "script_candidates": script_candidates,
        "static_detection": static,
        "supports_help": {"--help": bool(flags.get("--help")), "-help": bool(flags.get("-help"))},
        "supports_version_flags": {"--version": bool(flags.get("--version")), "-version": bool(flags.get("-version"))},
        "supports_project_run_parameters": False,
        "supports_script_mode": bool(flags.get("-script")),
        "short_start_exit": probe,
        "recommended_mode": "bundled_java_script" if executable and _app_root_for_executable(executable) and flags.get("-script") else ("launcher_script" if flags.get("-script") else "unavailable"),
        "confidence": "medium" if flags.get("-script") else "none",
        "warnings": [
            "HEC-HMS 4.13 exposes static -script evidence, but generated project syntax and compute results still require manual review.",
            "No direct project/run flags were inferred; HydroLite uses a generated Jython script instead.",
        ],
    }


def _run_name(hms_project_dir: Path, run_name: str | None) -> str:
    if run_name:
        return run_name
    run_file = hms_project_dir / "run" / "hydrolite_run.run"
    if run_file.exists():
        for line in run_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().lower().startswith("run:"):
                return line.split(":", 1)[1].strip()
    return "hydrolite_run"


def build_hms_run_command(
    hms_project_dir: str | Path,
    run_name: str | None = None,
    candidate: str | Path | None = None,
    mode: str = "auto",
) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    executable = str(_resolve(candidate)) if candidate else _first_hec_hms_executable()
    selected_run = _run_name(root, run_name)
    warnings: list[str] = []
    selected_mode = mode
    if not executable:
        selected_mode = "unavailable"
        warnings.append("No executable HEC-HMS candidate was detected.")
    elif mode == "auto":
        selected_mode = "script" if _hms_main_class_flags(executable)["flags"].get("-script") else "unavailable"
    elif mode in {"bundled_java_script", "launcher_script"}:
        selected_mode = "script"
    script = root / "scripts" / "hydrolite_run_hms.py"
    runtime: dict[str, Any] | None = None
    if executable and selected_mode == "script":
        runtime = _hms_script_runtime(executable, script)
        selected_mode = runtime["mode"]
    if runtime:
        command_executable = runtime["executable"]
        launcher = runtime["launcher"]
        args = runtime["args"]
        cwd = runtime["cwd"]
        environment = {**runtime["environment"], "HMS_PROJECT_DIR": str(root), "HMS_RUN_NAME": selected_run}
        confidence = runtime["confidence"]
    else:
        command_executable = executable or ""
        launcher = executable or ""
        args = []
        cwd = str(root)
        environment = {"HMS_PROJECT_DIR": str(root), "HMS_RUN_NAME": selected_run}
        confidence = "none"
    if not runtime:
        warnings.append("No verified command-line mode is available; command remains unavailable.")
    warnings.append("This command is an MVP candidate and must not be treated as production-verified HEC-HMS support.")
    command = ([command_executable] if command_executable else []) + args
    return {
        "executable": command_executable,
        "launcher": launcher,
        "args": args,
        "cwd": cwd,
        "environment": environment,
        "mode": selected_mode,
        "confidence": confidence,
        "warnings": warnings,
        "dry_run_command_string": shlex.join(command) if command else "",
        "project_file": str(root / f"{HMS_PROJECT_NAME}.hms"),
        "run_name": selected_run,
        "script_file": str(script),
    }


def write_hms_run_scripts(hms_project_dir: str | Path, output_dir: str | Path | None = None) -> dict[str, Path]:
    root = _resolve(hms_project_dir)
    scripts = _resolve(output_dir) if output_dir else root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    command = build_hms_run_command(root)
    project_file = root / f"{HMS_PROJECT_NAME}.hms"
    jython = scripts / "hydrolite_run_hms.py"
    shell = scripts / "run_hms.sh"
    batch = scripts / "run_hms.bat"
    jython.write_text(
        "\n".join(
            [
                "from hms.model import Project",
                f"project_path = {str(project_file)!r}",
                f"run_name = {command['run_name']!r}",
                "print 'HYDROLITE_HMS_RUN_START: ' + project_path",
                "Project.open(project_path)",
                "project = Project.getCurrentProject()",
                "if project is None:",
                "    raise Exception('HEC-HMS did not open the generated project')",
                "project.computeRun(run_name)",
                "Project.close()",
                "print 'HYDROLITE_HMS_RUN_COMPLETE: ' + run_name",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command = build_hms_run_command(root)
    if command["launcher"]:
        runtime = _hms_script_runtime(command["launcher"], jython)
        actual_command = [runtime["executable"], *runtime["args"]]
        script_environment = {**runtime["environment"], **command["environment"]}
    else:
        actual_command = []
        script_environment = command["environment"]
    shell_environment = "".join(
        f"export {key}={shlex.quote(str(value))}\n" for key, value in script_environment.items()
    )
    shell.write_text(
        "#!/bin/sh\nset -eu\n" + shell_environment
        + (shlex.join(actual_command) + "\n" if actual_command else 'echo "HEC-HMS executable unavailable" >&2\nexit 1\n'),
        encoding="utf-8",
    )
    shell.chmod(0o755)
    batch_environment = "".join(f"set {key}={value}\r\n" for key, value in script_environment.items())
    batch.write_text(
        batch_environment
        + (subprocess.list2cmdline(actual_command) + "\r\n" if actual_command else "echo HEC-HMS executable unavailable\r\nexit /b 1\r\n"),
        encoding="utf-8",
    )
    return {"jython": jython, "shell": shell, "batch": batch}


def _file_record(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "relative_path": str(path.relative_to(root)),
        "suffix": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def collect_hms_run_outputs(hms_project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    categories: dict[str, list[dict[str, Any]]] = {
        "logs": [], "out_files": [], "text_files": [], "dss_files": [], "hms_files": [], "run_files": [], "report_files": [], "other_files": []
    }
    if not root.is_dir():
        return {"status": "failed", "hms_project_dir": str(root), "error_message": "HEC-HMS project directory does not exist.", **categories}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        record = _file_record(root, path)
        relative = Path(record["relative_path"])
        suffix = path.suffix.lower()
        if suffix == ".log":
            categories["logs"].append(record)
        elif suffix == ".out":
            categories["out_files"].append(record)
        elif suffix == ".txt":
            categories["text_files"].append(record)
        elif suffix == ".dss":
            categories["dss_files"].append(record)
        elif suffix == ".hms":
            categories["hms_files"].append(record)
        elif relative.parts and relative.parts[0] == "run":
            categories["run_files"].append(record)
        elif relative.parts and relative.parts[0] == "reports":
            categories["report_files"].append(record)
        else:
            categories["other_files"].append(record)
    return {"status": "success", "hms_project_dir": str(root), **categories}


def parse_hms_logs(hms_project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    log_paths = sorted(root.rglob("*.log")) if root.is_dir() else []
    keywords = {name: [] for name in ("ERROR", "WARNING", "Simulation", "Compute", "DSS")}
    files: list[dict[str, Any]] = []
    for path in log_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:2_000_000]
            files.append({"path": str(path), "size_bytes": path.stat().st_size, "read_status": "success"})
            for line_number, line in enumerate(text.splitlines(), start=1):
                lowered = line.lower()
                for keyword in keywords:
                    if keyword.lower() in lowered and len(keywords[keyword]) < 100:
                        keywords[keyword].append({"file": str(path), "line": line_number, "text": line[:500]})
        except Exception as exc:  # noqa: BLE001
            files.append({"path": str(path), "size_bytes": 0, "read_status": "failed", "error": str(exc)})
    return {
        "status": "success" if files else "warning",
        "hms_project_dir": str(root),
        "log_files": files,
        "keyword_counts": {name: len(matches) for name, matches in keywords.items()},
        "matches": keywords,
        "message": "Log files parsed." if files else "No .log files were found; this is expected before execute or when HEC-HMS writes elsewhere.",
    }


def write_hms_run_report(hms_project_dir: str | Path, run_summary: dict[str, Any]) -> Path:
    root = _resolve(hms_project_dir)
    report = root / "reports" / "hec_hms_run_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    result = run_summary.get("run_result", run_summary)
    validation = run_summary.get("validation", {})
    log_summary = run_summary.get("log_summary", {})
    lines = [
        "# HydroLite HEC-HMS Run Probe MVP",
        "",
        "> 当前仅支持命令行能力探测、dry-run、短时 probe 和可选 execute。结果需要人工复核，DSS 深度读取仍为 planned。",
        "",
        f"- Status: `{result.get('status', 'unavailable')}`",
        f"- Runnable status: `{result.get('runnable_status', 'unavailable')}`",
        f"- Execute requested: `{result.get('execute_requested', False)}`",
        f"- Executable: `{result.get('command', {}).get('executable', '')}`",
        f"- Command: `{result.get('command', {}).get('dry_run_command_string', '')}`",
        f"- Return code: `{result.get('returncode')}`",
        f"- Timed out: `{result.get('timed_out', False)}`",
        f"- Validation: `{validation.get('status', 'pending')}`",
        f"- DSS files: `{run_summary.get('dss_count', 0)}`",
        "",
        "## Error and Output",
        "",
        f"- Error message: {result.get('error_message') or 'None'}",
        f"- stdout log: `{result.get('stdout_log', '')}`",
        f"- stderr log: `{result.get('stderr_log', '')}`",
        "",
        "## Log Keywords",
        "",
    ]
    for keyword, count in log_summary.get("keyword_counts", {}).items():
        lines.append(f"- {keyword}: `{count}`")
    lines.extend(
        [
            "",
            "## Next Steps",
            "",
            "1. Review generated basin/met/control/run files in HEC-HMS 4.13.",
            "2. Use an official minimal HEC-HMS project to verify the Jython `-script` compute API.",
            "3. Keep execute optional and timeout-bounded until project syntax is validated.",
            "4. Add DSS catalog/time-series reading in a later phase; absence of DSS is currently a warning.",
        ]
    )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def validate_hms_run_outputs(hms_project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    reports = root / "reports"
    result_file = reports / "hec_hms_run_result.json"
    report_file = reports / "hec_hms_run_report.md"
    summary_file = reports / "hec_hms_run_summary.xlsx"
    result: dict[str, Any] = {}
    if result_file.exists():
        try:
            result = json.loads(result_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            result = {}
    runnable_status = result.get("runnable_status", "unavailable")
    allowed = {"dry_run", "probe", "attempted", "executed", "failed", "unavailable", "completed_probe"}
    logs = list(root.rglob("*.log")) if root.is_dir() else []
    dss = list(root.rglob("*.dss")) if root.is_dir() else []
    checks = [
        {"check": "hec_hms_run_result.json", "passed": result_file.is_file(), "path": str(result_file)},
        {"check": "hec_hms_run_report.md", "passed": report_file.is_file(), "path": str(report_file)},
        {"check": "hec_hms_run_summary.xlsx", "passed": summary_file.is_file(), "path": str(summary_file)},
        {"check": "runnable_status", "passed": runnable_status in allowed, "value": runnable_status},
    ]
    errors = [row["check"] for row in checks if not row["passed"]]
    warnings = []
    if not logs:
        warnings.append("No log files were found.")
    if not dss:
        warnings.append("No DSS file was generated; DSS reading remains planned.")
    return {
        "status": "failed" if errors else "passed",
        "hms_project_dir": str(root),
        "runnable_status": runnable_status,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "log_files": [str(path) for path in logs],
        "dss_files": [str(path) for path in dss],
    }


def summarize_hms_run(hms_project_dir: str | Path, run_result: dict[str, Any] | None = None) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    result_path = reports / "hec_hms_run_result.json"
    if run_result is None and result_path.exists():
        try:
            run_result = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            run_result = {"status": "failed", "runnable_status": "failed", "error_message": str(exc)}
    run_result = run_result or {"status": "unavailable", "runnable_status": "unavailable", "error_message": "No run result exists."}
    outputs = collect_hms_run_outputs(root)
    log_summary = parse_hms_logs(root)
    summary: dict[str, Any] = {
        "generated_at": _now(),
        "hms_project_dir": str(root),
        "run_result": run_result,
        "outputs": outputs,
        "log_summary": log_summary,
        "dss_count": len(outputs.get("dss_files", [])),
        "dss_reading_status": "planned" if not outputs.get("dss_files") else "files_detected_not_parsed",
    }
    workbook = reports / "hec_hms_run_summary.xlsx"
    output_rows = [row | {"category": category} for category, rows in outputs.items() if isinstance(rows, list) for row in rows]
    keyword_rows = [
        {"keyword": keyword, "count": count} for keyword, count in log_summary.get("keyword_counts", {}).items()
    ]
    overview = {
        "status": run_result.get("status", "unavailable"),
        "runnable_status": run_result.get("runnable_status", "unavailable"),
        "execute_requested": run_result.get("execute_requested", False),
        "returncode": run_result.get("returncode"),
        "timed_out": run_result.get("timed_out", False),
        "executable": run_result.get("command", {}).get("executable", ""),
        "run_command": run_result.get("command", {}).get("dry_run_command_string", ""),
        "dss_count": summary["dss_count"],
        "dss_reading_status": summary["dss_reading_status"],
        "error_message": run_result.get("error_message", ""),
    }
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame([overview]).to_excel(writer, sheet_name="overview", index=False)
        pd.DataFrame(output_rows or [{"category": "none", "path": ""}]).to_excel(writer, sheet_name="outputs", index=False)
        pd.DataFrame(keyword_rows).to_excel(writer, sheet_name="log_keywords", index=False)
    summary["summary_xlsx"] = str(workbook)
    summary["validation"] = {
        "status": "pending",
        "runnable_status": run_result.get("runnable_status", "unavailable"),
    }
    report = write_hms_run_report(root, summary)
    summary["run_report"] = str(report)
    result_path.write_text(json.dumps(run_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary["run_result_json"] = str(result_path)
    summary["validation"] = validate_hms_run_outputs(root)
    write_hms_run_report(root, summary)
    return summary


def run_hms_project(
    hms_project_dir: str | Path,
    run_name: str | None = None,
    candidate: str | Path | None = None,
    timeout: int = 60,
    execute: bool = False,
) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    project_file = root / f"{HMS_PROJECT_NAME}.hms"
    command = build_hms_run_command(root, run_name, candidate)
    error_message = ""
    if not root.is_dir():
        return {
            "status": "failed", "runnable_status": "failed", "execute_requested": execute,
            "command": command, "returncode": None, "timed_out": False,
            "error_message": f"HEC-HMS project directory does not exist: {root}",
        }
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    scripts = write_hms_run_scripts(root)
    command = build_hms_run_command(root, run_name, candidate)
    if not project_file.is_file():
        error_message = f"HEC-HMS project file does not exist: {project_file}"
    elif command["mode"] == "unavailable":
        error_message = "HEC-HMS executable or script mode is unavailable."
    stdout = ""
    stderr = ""
    returncode: int | None = None
    timed_out = False
    if error_message:
        status = "failed"
        runnable_status = "unavailable" if command["mode"] == "unavailable" else "failed"
    elif not execute:
        status = "dry_run"
        runnable_status = "dry_run"
    else:
        attempt = _run_process_group(
            [command["executable"], *command["args"]],
            Path(command["cwd"]),
            timeout,
            environment=command["environment"],
        )
        stdout = attempt["stdout"]
        stderr = attempt["stderr"]
        returncode = attempt["returncode"]
        timed_out = attempt["timed_out"]
        if attempt["status"] == "completed":
            status = "executed"
            runnable_status = "executed"
        else:
            status = "failed"
            runnable_status = "failed"
            error_message = "HEC-HMS execution timed out." if timed_out else (stderr or "HEC-HMS returned a non-zero exit code.")
    stdout_log = reports / "hec_hms_run_stdout.log"
    stderr_log = reports / "hec_hms_run_stderr.log"
    activity_log = reports / "hec_hms_run.log"
    stdout_log.write_text(stdout + ("\n" if stdout else ""), encoding="utf-8")
    stderr_log.write_text(stderr + ("\n" if stderr else ""), encoding="utf-8")
    activity_log.write_text(
        "\n".join(
            [
                f"generated_at={_now()}",
                f"status={status}",
                f"runnable_status={runnable_status}",
                f"execute_requested={execute}",
                f"command={command['dry_run_command_string']}",
                f"error_message={error_message}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = {
        "generated_at": _now(),
        "status": status,
        "runnable_status": runnable_status,
        "execute_requested": execute,
        "simulation_attempted": execute,
        "command": command,
        "run_scripts": {name: str(path) for name, path in scripts.items()},
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": max(1, min(int(timeout), 60)),
        "stdout": stdout,
        "stderr": stderr,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "activity_log": str(activity_log),
        "error_message": error_message,
    }
    (reports / "hec_hms_run_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summarize_hms_run(root, result)
    return result


HMS_REFERENCE_ROOT = PROJECT_ROOT / "output" / "hec_hms_reference"
HMS_VERIFIED_ROOT = PROJECT_ROOT / "output" / "hec_hms_project_verified"
HMS_SAMPLE_ARCHIVE = Path("/Applications/HEC-HMS-4.13.app/Contents/Resources/samples.zip")
HMS_DSS_MIGRATOR = Path(
    "/Applications/HEC-HMS-4.13.app/Contents/Resources/bin/migrate-to-dss-7/bin/migrate-to-dss-7"
)


def _bounded_project_files(root: Path, max_depth: int = 7) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for current, directories, names in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        if depth >= max_depth:
            directories[:] = []
        for name in names:
            path = current_path / name
            if path.suffix.lower() in {".hms", ".basin", ".met", ".control", ".run"}:
                files.append(path)
                if len(files) >= 500:
                    return files
    return files


def _run_names_from_text(text: str) -> list[str]:
    return [line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Run:") and line.split(":", 1)[1].strip()]


def inspect_hms_reference_project(project_path: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(project_path, dict):
        source = str(project_path.get("project_path") or project_path.get("source_path") or "")
    else:
        source = str(project_path)
    warnings: list[str] = []
    counts = {suffix: 0 for suffix in (".hms", ".basin", ".met", ".control", ".run", ".dss")}
    run_names: list[str] = []
    total_size = 0
    total_files = 0
    hms_file = ""
    likely_official = False
    source_type = "directory"
    if "::" in source:
        archive_text, prefix = source.split("::", 1)
        archive = Path(archive_text)
        source_type = "archive"
        likely_official = archive.resolve() == HMS_SAMPLE_ARCHIVE.resolve()
        if not archive.is_file():
            warnings.append(f"Archive not found: {archive}")
        else:
            with zipfile.ZipFile(archive) as bundle:
                entries = [item for item in bundle.infolist() if not item.is_dir() and item.filename.startswith(prefix.rstrip("/") + "/")]
                total_files = len(entries)
                total_size = sum(item.file_size for item in entries)
                for item in entries:
                    suffix = Path(item.filename).suffix.lower()
                    if suffix in counts:
                        counts[suffix] += 1
                    if suffix == ".hms" and not hms_file:
                        hms_file = item.filename
                    if suffix == ".run":
                        run_names.extend(_run_names_from_text(bundle.read(item).decode("utf-8", errors="replace")))
    else:
        path = Path(source).expanduser().resolve()
        root = path.parent if path.is_file() else path
        files = [item for item in root.rglob("*") if item.is_file()]
        total_files = len(files)
        total_size = sum(item.stat().st_size for item in files)
        for item in files:
            suffix = item.suffix.lower()
            if suffix in counts:
                counts[suffix] += 1
            if suffix == ".hms" and not hms_file:
                hms_file = str(item)
            if suffix == ".run":
                run_names.extend(_run_names_from_text(item.read_text(encoding="utf-8", errors="replace")))
        likely_official = str(root).startswith("/Applications/HEC-HMS-4.13.app/")
    complete = all(counts[suffix] > 0 for suffix in (".hms", ".basin", ".met", ".control", ".run"))
    if not complete:
        warnings.append("Project is missing one or more basin/met/control/run components.")
    if counts[".dss"] == 0:
        warnings.append("No DSS file is bundled; compute may depend on missing time-series input.")
    dependency_risk = total_size > 20_000_000 or any(word in source.lower() for word in ("grid", "hrap", "forecast"))
    if dependency_risk:
        warnings.append("Project may be too large or depend on gridded/external data for a short compute probe.")
    project_name = Path(hms_file).stem if hms_file else Path(source.split("::")[-1]).name
    return {
        "project_path": source,
        "project_name": project_name,
        "source_type": source_type,
        "hms_file": hms_file,
        "basin_count": counts[".basin"],
        "met_count": counts[".met"],
        "control_count": counts[".control"],
        "run_count": counts[".run"],
        "dss_count": counts[".dss"],
        "total_files": total_files,
        "total_size_bytes": total_size,
        "run_names": sorted(set(run_names)),
        "likely_official": likely_official,
        "complete_components": complete,
        "suitable_for_short_compute": complete and bool(run_names) and not dependency_risk and total_size <= 20_000_000,
        "warnings": warnings,
    }


def discover_hms_reference_projects() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if HMS_SAMPLE_ARCHIVE.is_file():
        with zipfile.ZipFile(HMS_SAMPLE_ARCHIVE) as archive:
            prefixes = sorted({str(Path(item.filename).parent) for item in archive.infolist() if item.filename.lower().endswith(".hms")})
        for prefix in prefixes:
            candidates.append(inspect_hms_reference_project(f"{HMS_SAMPLE_ARCHIVE}::{prefix}"))
    roots = [
        Path.home() / "HEC-HMS",
        Path.home() / "Documents" / "HEC-HMS",
        Path.home() / "Documents" / "hms",
        PROJECT_ROOT / "output" / "hec_hms_project",
        PROJECT_ROOT / "output" / "hec_hms_project_verified",
    ]
    seen_roots: set[str] = set()
    for root in roots:
        for hms_file in _bounded_project_files(root):
            if hms_file.suffix.lower() != ".hms":
                continue
            project_root = str(hms_file.parent.resolve())
            if project_root in seen_roots:
                continue
            seen_roots.add(project_root)
            candidates.append(inspect_hms_reference_project(project_root))
            if len(candidates) >= 50:
                break
        if len(candidates) >= 50:
            break
    return candidates[:50]


def select_smallest_hms_reference_project(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [item for item in candidates if item.get("likely_official") and item.get("suitable_for_short_compute")]
    if not eligible:
        eligible = [item for item in candidates if item.get("complete_components") and item.get("run_names")]
    return min(eligible, key=lambda item: (item.get("total_size_bytes", 0), item.get("total_files", 0))) if eligible else None


def copy_hms_reference_project_to_output(project_path: str | Path | dict[str, Any], output_dir: str | Path) -> Path:
    source = project_path.get("project_path", "") if isinstance(project_path, dict) else str(project_path)
    target = _resolve(output_dir)
    output_root = (PROJECT_ROOT / "output").resolve()
    if target != output_root and output_root not in target.parents:
        raise ValueError(f"Official reference copies are restricted to output/: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    if "::" in source:
        archive_text, prefix = source.split("::", 1)
        with zipfile.ZipFile(Path(archive_text)) as archive:
            for item in archive.infolist():
                if item.is_dir() or not item.filename.startswith(prefix.rstrip("/") + "/"):
                    continue
                relative = Path(item.filename).relative_to(prefix)
                destination = (target / relative).resolve()
                if target not in destination.parents:
                    raise ValueError(f"Unsafe archive member: {item.filename}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source_handle, destination.open("wb") as target_handle:
                    shutil.copyfileobj(source_handle, target_handle)
    else:
        source_path = Path(source).expanduser().resolve()
        source_root = source_path.parent if source_path.is_file() else source_path
        shutil.copytree(source_root, target, dirs_exist_ok=True)
    return target


def prepare_hms_reference_dss_copy(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    output_root = (PROJECT_ROOT / "output").resolve()
    if root != output_root and output_root not in root.parents:
        return {
            "status": "skipped_outside_output",
            "message": "DSS migration is restricted to copied reference projects under output/.",
            "files": [],
        }
    dss_files = sorted(root.glob("*.dss"))
    if not HMS_DSS_MIGRATOR.is_file():
        return {
            "status": "unavailable",
            "message": f"HEC-HMS DSS migration utility not found: {HMS_DSS_MIGRATOR}",
            "files": [str(path) for path in dss_files],
        }
    versions: list[dict[str, Any]] = []
    version_six: list[Path] = []
    for path in dss_files:
        attempt = _run_process_group([str(HMS_DSS_MIGRATOR), "--version", str(path)], root, 30)
        version_text = attempt.get("stdout", "").strip().splitlines()
        version = version_text[-1].strip() if version_text else "unknown"
        versions.append({"path": str(path), "version_before": version})
        if version == "6":
            version_six.append(path)
    migration_attempt = None
    if version_six:
        migration_attempt = _run_process_group(
            [str(HMS_DSS_MIGRATOR), "--paths", *(str(path) for path in version_six)],
            root,
            60,
        )
    for row in versions:
        path = Path(row["path"])
        attempt = _run_process_group([str(HMS_DSS_MIGRATOR), "--version", str(path)], root, 30)
        version_text = attempt.get("stdout", "").strip().splitlines()
        row["version_after"] = version_text[-1].strip() if version_text else "unknown"
    migrated = [row for row in versions if row["version_before"] == "6" and row["version_after"] == "7"]
    failed = [row for row in versions if row["version_before"] == "6" and row["version_after"] != "7"]
    history_path = root.parent / "reports" / "reference_dss_migration.json"
    previous = None
    if history_path.exists():
        try:
            previous = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            previous = None
    result = {
        "status": "failed" if failed else ("migrated_to_dss7" if migrated else "not_required"),
        "message": "Official DSS v6 files were migrated only in the output/ working copy for macOS compatibility." if migrated else "No DSS v6 migration was required.",
        "utility": str(HMS_DSS_MIGRATOR),
        "files": versions,
        "migration_attempt": migration_attempt,
    }
    if migrated:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif previous and previous.get("status") == "migrated_to_dss7":
        result["status"] = "already_migrated_to_dss7"
        result["message"] = "DSS v6 files were migrated in an earlier probe of this output/ working copy."
        result["previous_migration"] = previous
    return result


def discover_hms_run_names(project_dir: str | Path) -> list[str]:
    root = _resolve(project_dir)
    names: list[str] = []
    for path in sorted(root.glob("*.run")):
        names.extend(_run_names_from_text(path.read_text(encoding="utf-8", errors="replace")))
    return sorted(set(names))


def _jython_unicode_literal(value: str | Path) -> str:
    escaped = str(value).encode("unicode_escape").decode("ascii").replace("'", "\\'")
    return f"u'{escaped}'"


def _ascii_safe_hms_project_file(project_file: Path) -> Path:
    try:
        str(project_file).encode("ascii")
        return project_file
    except UnicodeEncodeError:
        digest = hashlib.sha256(str(project_file.parent).encode("utf-8")).hexdigest()[:12]
        alias_root = Path(tempfile.gettempdir()) / "hydrolite_hms_paths"
        alias_root.mkdir(parents=True, exist_ok=True)
        alias = alias_root / digest
        if alias.is_symlink() and alias.resolve() != project_file.parent.resolve():
            alias.unlink()
        elif alias.exists() and not alias.is_symlink():
            raise RuntimeError(f"HEC-HMS ASCII path alias is occupied: {alias}")
        if not alias.exists():
            alias.symlink_to(project_file.parent, target_is_directory=True)
        return alias / project_file.name


def _write_hms_open_script(project_dir: Path, output_path: Path, run_names: list[str]) -> Path:
    project_file = next(iter(sorted(project_dir.glob("*.hms"))), None)
    if not project_file:
        raise FileNotFoundError(f"No .hms project file found in {project_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# -*- coding: ascii -*-",
        "from hms.model import Project",
        "from hms import Hms",
        f"project_path = {_jython_unicode_literal(_ascii_safe_hms_project_file(project_file))}",
        "project = None",
        "try:",
        "    project = Project.open(project_path)",
        "    if project is None:",
        "        raise Exception('Project.open returned None')",
        "    print 'HYDROLITE_HMS_PROJECT_OPENED'",
    ]
    lines.extend(f"    print 'HYDROLITE_HMS_RUN: {name}'" for name in run_names)
    lines.extend(
        [
            "finally:",
            "    if project is not None:",
            "        project.close()",
            "        print 'HYDROLITE_HMS_PROJECT_CLOSED'",
            "    Hms.shutdownEngine()",
            "    print 'HYDROLITE_HMS_ENGINE_SHUTDOWN'",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def build_official_hms_compute_script(project_dir: str | Path, run_name: str, output_path: str | Path) -> Path:
    root = _resolve(project_dir)
    project_file = next(iter(sorted(root.glob("*.hms"))), None)
    if not project_file:
        raise FileNotFoundError(f"No .hms project file found in {root}")
    output = _resolve(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(
            [
                "# -*- coding: ascii -*-",
                "from hms.model import Project",
                "from hms import Hms",
                f"project_path = {_jython_unicode_literal(_ascii_safe_hms_project_file(project_file))}",
                f"run_name = {run_name!r}",
                "project = None",
                "try:",
                "    project = Project.open(project_path)",
                "    if project is None:",
                "        raise Exception('Project.open returned None')",
                "    print 'HYDROLITE_HMS_PROJECT_OPENED'",
                "    project.computeRun(run_name)",
                "    print 'HYDROLITE_HMS_COMPUTE_RETURNED'",
                "finally:",
                "    if project is not None:",
                "        project.close()",
                "        print 'HYDROLITE_HMS_PROJECT_CLOSED'",
                "    Hms.shutdownEngine()",
                "    print 'HYDROLITE_HMS_ENGINE_SHUTDOWN'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def build_legacy_hms_compute_script(project_dir: str | Path, run_name: str, output_path: str | Path) -> Path:
    root = _resolve(project_dir)
    project_file = next(iter(sorted(root.glob("*.hms"))), None)
    if not project_file:
        raise FileNotFoundError(f"No .hms project file found in {root}")
    output = _resolve(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(
            [
                "# -*- coding: ascii -*-",
                "from hms.model.JythonHms import *",
                f"OpenProject({project_file.stem!r}, {_jython_unicode_literal(_ascii_safe_hms_project_file(project_file).parent)})",
                f"Compute({run_name!r})",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def _run_hms_script(script: Path, project_dir: Path, timeout: int) -> dict[str, Any]:
    launcher = _first_hec_hms_executable()
    if not launcher:
        return {"status": "unavailable", "returncode": None, "stdout": "", "stderr": "HEC-HMS executable unavailable.", "timed_out": False, "runtime_seconds": 0.0}
    runtime = _hms_script_runtime(launcher, script)
    command = [runtime["executable"], *runtime["args"]]
    started = time.monotonic()
    attempt = _run_process_group(command, project_dir, min(max(timeout, 1), 120), runtime["environment"])
    return {**attempt, "command": command, "mode": runtime["mode"], "runtime_seconds": time.monotonic() - started}


def _file_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns) for path in root.rglob("*") if path.is_file()}


def collect_official_hms_reference_outputs(project_dir: str | Path) -> dict[str, Any]:
    root = _resolve(project_dir)
    return collect_hms_run_outputs(root)


def write_official_hms_reference_report(output_dir: str | Path, result: dict[str, Any]) -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "hec_hms_official_reference_result.json"
    md_path = output / "hec_hms_official_reference_report.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# HEC-HMS Official Reference Validation",
        "",
        "> The copied official sample is local validation material under output/ and is not committed to the repository.",
        "",
        f"- Project: `{result.get('project_name', '')}`",
        f"- Project directory: `{result.get('project_dir', '')}`",
        f"- Run name: `{result.get('run_name', '')}`",
        f"- Open status: `{result.get('open_status', 'not_run')}`",
        f"- Compute status: `{result.get('compute_status', 'not_run')}`",
        f"- Return code: `{result.get('returncode')}`",
        f"- Runtime seconds: `{result.get('runtime_seconds', 0):.3f}`",
        f"- New or modified DSS: `{len(result.get('changed_dss_files', []))}`",
        f"- DSS compatibility preparation: `{result.get('dss_migration', {}).get('status', 'not_checked')}`",
        f"- Fatal errors: `{len(result.get('fatal_errors', []))}`",
        f"- Process cleanup confirmed: `{result.get('process_cleanup_confirmed', False)}`",
        "",
        "## Warnings",
        "",
    ]
    lines.extend(f"- {warning}" for warning in result.get("warnings", []))
    lines.extend(["", "## Fatal Errors", ""])
    lines.extend(f"- {error}" for error in result.get("fatal_errors", []))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def run_official_hms_reference(
    project_dir: str | Path,
    run_name: str | None = None,
    execute: bool = False,
    timeout: int = 120,
) -> dict[str, Any]:
    root = _resolve(project_dir)
    base = root.parent
    scripts = base / "scripts"
    reports = base / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    names = discover_hms_run_names(root)
    selected_run = run_name or (names[0] if names else "")
    dss_migration = prepare_hms_reference_dss_copy(root)
    open_script = _write_hms_open_script(root, scripts / "open_reference_project.py", names)
    compute_script = build_official_hms_compute_script(root, selected_run, scripts / "compute_reference_run.py") if selected_run else None
    legacy_script = build_legacy_hms_compute_script(root, selected_run, scripts / "compute_reference_run_legacy.py") if selected_run else None
    before = _file_snapshot(root)
    open_attempt = _run_hms_script(open_script, root, min(timeout, 60))
    open_text = f"{open_attempt.get('stdout', '')}\n{open_attempt.get('stderr', '')}"
    fatal_errors = _fatal_hms_lines(open_text)
    open_success = (
        open_attempt.get("returncode") == 0
        and "HYDROLITE_HMS_PROJECT_OPENED" in open_text
        and "HYDROLITE_HMS_PROJECT_CLOSED" in open_text
        and not fatal_errors
    )
    compute_attempt: dict[str, Any] | None = None
    if execute and open_success and selected_run and compute_script:
        compute_attempt = _run_hms_script(compute_script, root, min(timeout, 120))
    after = _file_snapshot(root)
    changed = [name for name, metadata in after.items() if before.get(name) != metadata]
    changed_dss = [str(root / name) for name in changed if Path(name).suffix.lower() == ".dss"]
    compute_text = f"{(compute_attempt or {}).get('stdout', '')}\n{(compute_attempt or {}).get('stderr', '')}"
    compute_fatal = _fatal_hms_lines(compute_text)
    fatal_errors.extend(compute_fatal)
    if not execute:
        compute_status = "not_requested"
    elif not open_success:
        compute_status = "skipped_open_failed"
    elif not selected_run:
        compute_status = "skipped_run_not_found"
    elif compute_attempt and compute_attempt.get("timed_out"):
        compute_status = "timeout"
    elif compute_attempt and compute_attempt.get("returncode") == 0 and "HYDROLITE_HMS_COMPUTE_RETURNED" in compute_text and not compute_fatal:
        compute_status = "compute_completed"
    else:
        compute_status = "compute_failed"
    active = compute_attempt or open_attempt
    result = {
        "generated_at": _now(),
        "project_name": next(iter(root.glob("*.hms")), root).stem,
        "project_dir": str(root),
        "run_names": names,
        "run_name": selected_run,
        "execute_requested": execute,
        "open_status": "project_opened" if open_success else ("timeout" if open_attempt.get("timed_out") else "open_failed"),
        "compute_status": compute_status,
        "returncode": active.get("returncode"),
        "runtime_seconds": active.get("runtime_seconds", 0.0),
        "open_attempt": open_attempt,
        "compute_attempt": compute_attempt,
        "changed_files": [str(root / name) for name in changed],
        "changed_dss_files": changed_dss,
        "outputs": collect_official_hms_reference_outputs(root),
        "dss_migration": dss_migration,
        "fatal_errors": fatal_errors,
        "process_cleanup_confirmed": bool(active.get("process_terminated")),
        "engine_shutdown_status": "clean_process_exit_after_project_close" if active.get("process_terminated") and active.get("returncode") == 0 else "unconfirmed",
        "warnings": [] if open_success else ["Official reference open failed; compute was not allowed."],
        "scripts": {
            "open": str(open_script),
            "compute": str(compute_script) if compute_script else "",
            "legacy_compatibility": str(legacy_script) if legacy_script else "",
        },
    }
    (reports / "reference_stdout.log").write_text(active.get("stdout", "") + "\n", encoding="utf-8")
    (reports / "reference_stderr.log").write_text(active.get("stderr", "") + "\n", encoding="utf-8")
    result["report_files"] = {name: str(path) for name, path in write_official_hms_reference_report(reports, result).items()}
    return result


def _hms_date_time() -> tuple[str, str]:
    now = datetime.now()
    return now.strftime("%d %B %Y").lstrip("0"), now.strftime("%H:%M:%S")


def _write_calibrated_hms_files(project_data: dict[str, Any], root: Path) -> dict[str, Path]:
    date_text, time_text = _hms_date_time()
    project_name = HMS_PROJECT_NAME
    basin_name = "hydrolite_basin"
    met_name = "hydrolite_meteorologic"
    control_name = "hydrolite_control"
    run_name = "hydrolite_run"
    project_file = root / f"{project_name}.hms"
    basin_file = root / f"{basin_name}.basin"
    met_file = root / f"{met_name}.met"
    control_file = root / f"{control_name}.control"
    # HEC-HMS discovers simulation runs from a project-named .run file.
    run_file = root / f"{project_name}.run"
    project_file.write_text(
        "\n".join(
            [
                f"Project: {project_name}",
                "     Description: HydroLite Studio generated project for HEC-HMS format validation",
                "     Version: 4.13",
                "     Filepath Separator: /",
                f"     DSS File Name: {project_name}.dss",
                "     Time Zone ID: Etc/UTC",
                "End:",
                "",
                f"Precipitation: {met_name}",
                f"     Filename: {met_file.name}",
                "     Description: HydroLite meteorologic model",
                f"     Last Modified Date: {date_text}",
                f"     Last Modified Time: {time_text}",
                "End:",
                "",
                f"Basin: {basin_name}",
                f"     Filename: {basin_file.name}",
                "     Description: HydroLite basin model",
                f"     Last Modified Date: {date_text}",
                f"     Last Modified Time: {time_text}",
                "End:",
                "",
                f"Control: {control_name}",
                f"     FileName: {control_file.name}",
                "     Description: HydroLite control specifications",
                "End:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    basin_lines = [
        f"Basin: {basin_name}",
        "     Description: HydroLite basin model calibrated from generic HEC-HMS 4.13 structure",
        f"     Last Modified Date: {date_text}",
        f"     Last Modified Time: {time_text}",
        "     Version: 4.13",
        "     Filepath Separator: /",
        "     Unit System: Metric",
        "     Missing Flow To Zero: No",
        "     Enable Flow Ratio: No",
        "     Compute Local Flow At Junctions: No",
        "     Unregulated Output Required: No",
        "",
        "     Enable Sediment Routing: No",
        "End:",
    ]
    reaches = project_data["reaches"]
    first_reach = str(_value(reaches.iloc[0], ("reach_id", "id"), "R1")) if not reaches.empty else ""
    for index, (_, row) in enumerate(project_data["subbasins"].iterrows(), start=1):
        subbasin_id = str(_value(row, ("subbasin_id", "id"), f"S{index}"))
        downstream = first_reach or "Outlet"
        lag_minutes = max(0.0, float(_value(row, ("lag_time_hr", "lag_hours"), 1.0)) * 60.0)
        basin_lines.extend(
            [
                "",
                f"Subbasin: {subbasin_id}",
                f"     Last Modified Date: {date_text}",
                f"     Last Modified Time: {time_text}",
                f"     Canvas X: {1000.0 + index * 100.0:.3f}",
                f"     Canvas Y: {1000.0 + index * 100.0:.3f}",
                f"     Area: {float(_value(row, ('area_km2',), 1.0)):.6f}",
                f"     Downstream: {downstream}",
                "",
                "     Discretization: None",
                "",
                "     Canopy: None",
                "     Allow Simultaneous Precip Et: No",
                "     Plant Uptake Method: None",
                "",
                "     Surface: None",
                "",
                "     LossRate: SCS Curve Number",
                f"     Curve Number: {float(_value(row, ('cn',), 75.0)):.3f}",
                "     Initial Abstraction: 0",
                "",
                "     Transform: SCS",
                f"     Lag: {lag_minutes:.3f}",
                "     Unitgraph Type: STANDARD",
                "",
                "     Baseflow: None",
                "End:",
            ]
        )
    for index, (_, row) in enumerate(reaches.iterrows(), start=1):
        reach_id = str(_value(row, ("reach_id", "id"), f"R{index}"))
        reach_ids = {str(_value(item, ("reach_id", "id"), "")) for _, item in reaches.iterrows()}
        candidate_downstream = str(_value(row, ("downstream_reach_id",), ""))
        downstream = candidate_downstream if candidate_downstream in reach_ids else "Outlet"
        basin_lines.extend(
            [
                "",
                f"Reach: {reach_id}",
                f"     Last Modified Date: {date_text}",
                f"     Last Modified Time: {time_text}",
                f"     Canvas X: {1500.0 + index * 100.0:.3f}",
                f"     Canvas Y: {800.0 - index * 50.0:.3f}",
                f"     From Canvas X: {1200.0 + index * 100.0:.3f}",
                f"     From Canvas Y: {1000.0 - index * 50.0:.3f}",
                f"     Downstream: {downstream}",
                "",
                "     Route: Muskingum",
                "     Initial Variable: Combined Inflow",
                f"     Muskingum K: {float(_value(row, ('muskingum_k_hr', 'k_hours'), 1.0)):.6f}",
                f"     Muskingum x: {float(_value(row, ('muskingum_x', 'x'), 0.2)):.6f}",
                "     Muskingum Steps: 1",
                "     Channel Loss: None",
                "End:",
            ]
        )
    basin_lines.extend(
        [
            "",
            "Junction: Outlet",
            f"     Last Modified Date: {date_text}",
            f"     Last Modified Time: {time_text}",
            "     Canvas X: 1800.000",
            "     Canvas Y: 500.000",
            "End:",
        ]
    )
    basin_file.write_text("\n".join(basin_lines) + "\n", encoding="utf-8")
    met_lines = [
        f"Meteorology: {met_name}",
        "     Description: No-precipitation model for project-open validation",
        f"     Last Modified Date: {date_text}",
        f"     Last Modified Time: {time_text}",
        "     Version: 4.13",
        "     Unit System: Metric",
        "     Set Missing Data to Default: Yes",
        "     Precipitation Method: None",
        "     Air Temperature Method: None",
        "     Atmospheric Pressure Method: None",
        "     Dew Point Method: None",
        "     Wind Speed Method: None",
        "     Shortwave Radiation Method: None",
        "     Longwave Radiation Method: None",
        "     Snowmelt Method: None",
        "     Evapotranspiration Method: No Evapotranspiration",
        f"     Use Basin Model: {basin_name}",
        "End:",
    ]
    met_file.write_text("\n".join(met_lines) + "\n", encoding="utf-8")
    start, end, dt_minutes, warnings = _control_period(project_data)
    project_data.setdefault("warnings", []).extend(warnings)
    control_file.write_text(
        "\n".join(
            [
                f"Control: {control_name}",
                "     Description: HydroLite inferred control specifications",
                f"     Last Modified Date: {date_text}",
                f"     Last Modified Time: {time_text}",
                "     Version: 4.13",
                f"     Start Date: {start:%d %B %Y}",
                f"     Start Time: {start:%H:%M}",
                f"     End Date: {end:%d %B %Y}",
                f"     End Time: {end:%H:%M}",
                f"     Time Interval: {dt_minutes}",
                "End:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_content = (
        "\n".join(
            [
                f"Run: {run_name}",
                "     Description: HydroLite generated run for format validation",
                f"     Log File: {run_name}.log",
                f"     DSS File: {run_name}.dss",
                "     Is Save Spatial Results: No",
                f"     Last Modified Date: {date_text}",
                f"     Last Modified Time: {time_text}",
                f"     Basin: {basin_name}",
                f"     Precip: {met_name}",
                f"     Control: {control_name}",
                "     Save State Type: None",
                "     Time-Series Output: Save All",
                "     Time Series Results Manager Start:",
                "     Time Series Results Manager End:",
                "End:",
            ]
        )
        + "\n"
    )
    run_file.write_text(run_content, encoding="utf-8")
    compatibility_run = root / f"{run_name}.run"
    compatibility_run.write_text(run_content, encoding="utf-8")
    return {
        "project": project_file,
        "basin": basin_file,
        "meteorologic": met_file,
        "control": control_file,
        "run": run_file,
        "run_compatibility_copy": compatibility_run,
    }


def build_hms_open_script(hms_project_dir: str | Path, output_path: str | Path) -> Path:
    root = _resolve(hms_project_dir)
    return _write_hms_open_script(root, _resolve(output_path), discover_hms_run_names(root))


def create_calibrated_hms_project_from_hydrolite(
    project_dir: str | Path,
    output_dir: str | Path = HMS_VERIFIED_ROOT,
    reference_dir: str | Path = HMS_REFERENCE_ROOT / "reference_project",
) -> dict[str, Any]:
    from hydrolite.hec_hms_format import compare_generated_to_reference, validate_hms_component_syntax, write_hms_format_comparison_report

    root = _resolve(output_dir)
    if root.exists():
        shutil.rmtree(root)
    (root / "scripts").mkdir(parents=True)
    (root / "reports").mkdir()
    project_data = collect_hydrolite_project_for_hms(project_dir)
    files = _write_calibrated_hms_files(project_data, root)
    open_script = build_hms_open_script(root, root / "scripts" / "open_generated_project.py")
    run_names = discover_hms_run_names(root)
    compute_script = build_official_hms_compute_script(root, run_names[0], root / "scripts" / "compute_generated_project.py") if run_names else None
    validation = validate_hms_component_syntax(root)
    reference = _resolve(reference_dir)
    comparison = compare_generated_to_reference(reference, root)
    comparison_outputs = write_hms_format_comparison_report(root / "reports", comparison)
    comparison_xlsx = root / "reports" / "hec_hms_reference_comparison.xlsx"
    shutil.copy2(comparison_outputs["xlsx"], comparison_xlsx)
    validation_result = {
        "status": validation["status"],
        "validation_level": "syntax_compared",
        "source_project": str(_resolve(project_dir)),
        "calibrated_project": str(root),
        "generated_files": {name: str(path) for name, path in files.items()},
        "run_names": run_names,
        "syntax_validation": validation,
        "comparison_status": comparison["status"],
        "calibration_findings": comparison["calibration_findings"],
        "warnings": project_data.get("warnings", []) + ["Project.open and computeRun require separate runtime probes."],
        "scripts": {"open": str(open_script), "compute": str(compute_script) if compute_script else ""},
    }
    validation_json = root / "reports" / "hec_hms_format_validation.json"
    validation_md = root / "reports" / "hec_hms_format_validation.md"
    validation_json.write_text(json.dumps(validation_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    validation_md.write_text(
        "\n".join(
            [
                "# Calibrated HEC-HMS Project Format Validation",
                "",
                f"- Status: `{validation['status']}`",
                "- Validation level: `syntax_compared`",
                f"- Run names: `{', '.join(run_names)}`",
                f"- Reference comparison: `{comparison['status']}`",
                "",
                "The project uses generic syntax patterns derived from HEC-HMS 4.13 component structure. No official sample data was copied into repository templates.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    validation_result["reports"] = {
        "validation_json": str(validation_json),
        "validation_markdown": str(validation_md),
        "comparison_xlsx": str(comparison_xlsx),
        "comparison_markdown": str(comparison_outputs["markdown"]),
    }
    return validation_result


def _fatal_hms_lines(text: str) -> list[str]:
    fatal: list[str] = []
    for line in text.splitlines():
        upper = line.upper()
        if not any(token in upper for token in ("EXCEPTION", "FATAL", "ERROR")):
            continue
        if any(clean in upper for clean in ("0 ERROR", "ERROR COUNT: 0", "NO ERROR")):
            continue
        fatal.append(line)
    return fatal


def run_hms_open_probe(hms_project_dir: str | Path, timeout: int = 60) -> dict[str, Any]:
    root = _resolve(hms_project_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    script = build_hms_open_script(root, root / "scripts" / "open_generated_project.py")
    attempt = _run_hms_script(script, root, min(timeout, 60))
    text = f"{attempt.get('stdout', '')}\n{attempt.get('stderr', '')}"
    fatal = _fatal_hms_lines(text)
    opened = (
        attempt.get("returncode") == 0
        and "HYDROLITE_HMS_PROJECT_OPENED" in text
        and "HYDROLITE_HMS_PROJECT_CLOSED" in text
        and not fatal
    )
    run_names = discover_hms_run_names(root)
    result = {
        "status": "project_opened" if opened else ("timeout" if attempt.get("timed_out") else "open_failed"),
        "validation_level": "run_discovered" if opened and run_names else ("project_opened" if opened else "syntax_compared"),
        "project_dir": str(root),
        "run_names": run_names,
        "returncode": attempt.get("returncode"),
        "runtime_seconds": attempt.get("runtime_seconds", 0.0),
        "fatal_errors": fatal,
        "process_cleanup_confirmed": bool(attempt.get("process_terminated")),
        "engine_shutdown_status": "clean_process_exit_after_project_close" if attempt.get("process_terminated") and attempt.get("returncode") == 0 else "unconfirmed",
        "warnings": [] if opened else ["Generated project did not pass the strict Project.open gate."],
        "attempt": attempt,
        "script": str(script),
    }
    json_path = reports / "hec_hms_open_probe.json"
    md_path = reports / "hec_hms_open_probe.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "generated_open_stdout.log").write_text(attempt.get("stdout", "") + "\n", encoding="utf-8")
    (reports / "generated_open_stderr.log").write_text(attempt.get("stderr", "") + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Generated HEC-HMS Project Open Probe",
                "",
                f"- Status: `{result['status']}`",
                f"- Validation level: `{result['validation_level']}`",
                f"- Return code: `{result['returncode']}`",
                f"- Run names: `{', '.join(run_names)}`",
                f"- Fatal errors: `{len(fatal)}`",
                "",
                "Project-open success is not simulation completion.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result["report_files"] = {"json": str(json_path), "markdown": str(md_path)}
    return result


def inspect_hms_compute_readiness(hms_project_dir: str | Path) -> dict[str, Any]:
    from hydrolite.hec_hms_format import (
        parse_hms_basin_file,
        parse_hms_control_file,
        parse_hms_meteorologic_file,
    )

    root = _resolve(hms_project_dir)
    met_path = next(iter(sorted(root.glob("*.met"))), None)
    basin_path = next(iter(sorted(root.glob("*.basin"))), None)
    control_path = next(iter(sorted(root.glob("*.control"))), None)
    findings: list[str] = []

    rainfall_ready = False
    if met_path:
        meteorology = parse_hms_meteorologic_file(met_path)
        methods = [
            str(block.get("property_map", {}).get("Precipitation Method", [""])[0]).strip()
            for block in meteorology.get("blocks", [])
        ]
        rainfall_ready = any(method and method.lower() not in {"none", "undefined"} for method in methods)
    if not rainfall_ready:
        findings.append("Meteorologic model has no runnable precipitation method; rainfall input is not compute-ready.")

    topology_ready = False
    if basin_path:
        basin = parse_hms_basin_file(basin_path)
        element_types = {"Subbasin", "Reach", "Junction", "Reservoir", "Source", "Sink", "Diversion"}
        elements = {
            str(block.get("name", ""))
            for block in basin.get("blocks", [])
            if block.get("block_type") in element_types
        }
        broken_links = []
        for block in basin.get("blocks", []):
            downstream = str(block.get("property_map", {}).get("Downstream", [""])[0]).strip()
            if downstream and downstream not in elements:
                broken_links.append(f"{block.get('block_type')} {block.get('name')} -> {downstream}")
        topology_ready = bool(elements) and not broken_links
        if broken_links:
            findings.extend(f"Invalid basin topology link: {link}" for link in broken_links)
    if not topology_ready and not any(item.startswith("Invalid basin topology") for item in findings):
        findings.append("Basin topology could not be verified.")

    control_period_valid = False
    calculation_interval_valid = False
    if control_path:
        control = parse_hms_control_file(control_path)
        properties = next((block.get("property_map", {}) for block in control.get("blocks", []) if block.get("block_type") == "Control"), {})
        start = pd.to_datetime(
            f"{properties.get('Start Date', [''])[0]} {properties.get('Start Time', [''])[0]}", errors="coerce"
        )
        end = pd.to_datetime(
            f"{properties.get('End Date', [''])[0]} {properties.get('End Time', [''])[0]}", errors="coerce"
        )
        control_period_valid = pd.notna(start) and pd.notna(end) and end > start
        try:
            interval = float(properties.get("Time Interval", [0])[0])
        except (TypeError, ValueError):
            interval = 0
        calculation_interval_valid = interval > 0 and (not control_period_valid or interval <= (end - start).total_seconds() / 60)
    if not control_period_valid:
        findings.append("Control period is missing or invalid.")
    if not calculation_interval_valid:
        findings.append("Calculation interval is missing, non-positive, or longer than the control period.")

    return {
        "rainfall_ready": rainfall_ready,
        "topology_ready": topology_ready,
        "control_period_valid": bool(control_period_valid),
        "calculation_interval_valid": calculation_interval_valid,
        "findings": findings,
    }


def run_hms_compute_probe(
    hms_project_dir: str | Path,
    run_name: str | None = None,
    timeout: int = 120,
    execute: bool = False,
) -> dict[str, Any]:
    from hydrolite.hec_hms_format import validate_hms_component_syntax

    root = _resolve(hms_project_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    open_result = run_hms_open_probe(root, min(timeout, 60))
    run_names = discover_hms_run_names(root)
    selected_run = run_name or (run_names[0] if run_names else "")
    syntax = validate_hms_component_syntax(root)
    readiness = inspect_hms_compute_readiness(root)
    total_size = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    gates = {
        "project_opened": open_result["status"] == "project_opened",
        "run_discovered": bool(selected_run),
        "component_references_complete": syntax["status"] == "passed",
        "no_fatal_open_errors": not open_result["fatal_errors"],
        "small_project": total_size <= 10_000_000,
        "timeout_safe": 0 < timeout <= 120,
        "rainfall_ready": readiness["rainfall_ready"],
        "control_period_valid": readiness["control_period_valid"],
        "calculation_interval_valid": readiness["calculation_interval_valid"],
        "basin_topology_valid": readiness["topology_ready"],
    }
    script = build_official_hms_compute_script(root, selected_run, root / "scripts" / "compute_generated_project.py") if selected_run else None
    before = _file_snapshot(root)
    attempt = _run_hms_script(script, root, min(timeout, 120)) if execute and all(gates.values()) and script else None
    after = _file_snapshot(root)
    changed = [name for name, metadata in after.items() if before.get(name) != metadata]
    text = f"{(attempt or {}).get('stdout', '')}\n{(attempt or {}).get('stderr', '')}"
    fatal = _fatal_hms_lines(text)
    if not execute:
        status = "skipped_execute_not_requested"
        level = open_result["validation_level"]
    elif not all(gates.values()):
        status = "skipped_gate_failed"
        level = open_result["validation_level"]
    elif attempt and attempt.get("timed_out"):
        status = "timeout"
        level = "compute_failed"
    elif attempt and attempt.get("returncode") == 0 and "HYDROLITE_HMS_COMPUTE_RETURNED" in text and not fatal:
        status = "compute_completed"
        level = "compute_completed"
    else:
        status = "compute_failed"
        level = "compute_failed"
    result = {
        "status": status,
        "validation_level": level,
        "project_dir": str(root),
        "run_name": selected_run,
        "execute_requested": execute,
        "gates": gates,
        "returncode": (attempt or {}).get("returncode"),
        "runtime_seconds": (attempt or {}).get("runtime_seconds", 0.0),
        "fatal_errors": fatal,
        "warnings": [name for name, passed in gates.items() if not passed],
        "readiness": readiness,
        "attempt": attempt,
        "changed_files": [str(root / name) for name in changed],
        "changed_dss_files": [str(root / name) for name in changed if Path(name).suffix.lower() == ".dss"],
        "open_result": open_result,
        "script": str(script) if script else "",
    }
    json_path = reports / "hec_hms_compute_probe.json"
    md_path = reports / "hec_hms_compute_probe.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if attempt:
        (reports / "generated_compute_stdout.log").write_text(attempt.get("stdout", "") + "\n", encoding="utf-8")
        (reports / "generated_compute_stderr.log").write_text(attempt.get("stderr", "") + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Generated HEC-HMS Compute Probe",
                "",
                f"- Status: `{status}`",
                f"- Validation level: `{level}`",
                f"- Run: `{selected_run}`",
                f"- Return code: `{result['returncode']}`",
                f"- New or modified DSS: `{len(result['changed_dss_files'])}`",
                "",
                "## Compute Readiness",
                "",
                *(f"- {finding}" for finding in readiness["findings"]),
                "",
                "Compute success is based on the real process result and script marker; no DSS file is fabricated.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result["report_files"] = {"json": str(json_path), "markdown": str(md_path)}
    return result


def classify_hms_validation_level(
    reference_result: dict[str, Any] | None,
    open_result: dict[str, Any] | None,
    compute_result: dict[str, Any] | None = None,
) -> str:
    if compute_result and compute_result.get("status") == "compute_completed":
        return "compute_completed"
    if compute_result and compute_result.get("status") in {"compute_failed", "timeout"}:
        return "compute_failed"
    if compute_result and compute_result.get("attempt") is not None:
        return "compute_attempted"
    if open_result and open_result.get("status") == "project_opened" and open_result.get("run_names"):
        return "run_discovered"
    if open_result and open_result.get("status") == "project_opened":
        return "project_opened"
    if reference_result and reference_result.get("open_status") == "project_opened":
        return "syntax_compared"
    return "generated_only" if open_result else "unavailable"


def discover_hms_dss_files(project_dir: str | Path) -> list[Path]:
    root = _resolve(project_dir)
    return sorted(path for path in root.rglob("*.dss") if path.is_file()) if root.is_dir() else []


def inspect_hms_dss_file_metadata(dss_path: str | Path) -> dict[str, Any]:
    path = _resolve(dss_path)
    stat = path.stat()
    lower_parts = {part.lower() for part in path.parts}
    role = "output" if "results" in lower_parts or "output" in lower_parts or path.with_suffix(".log").exists() else "input_or_unknown"
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "created_this_run": "unknown",
        "is_empty": stat.st_size == 0,
        "possible_role": role,
        "read_status": "metadata_only",
    }


def write_hms_dss_discovery_report(project_dir: str | Path) -> dict[str, Path]:
    root = _resolve(project_dir)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    rows = [inspect_hms_dss_file_metadata(path) for path in discover_hms_dss_files(root)]
    compute_result_path = reports / "hec_hms_compute_probe.json"
    changed: set[str] = set()
    if compute_result_path.exists():
        try:
            changed = set(json.loads(compute_result_path.read_text(encoding="utf-8")).get("changed_dss_files", []))
        except Exception:  # noqa: BLE001
            changed = set()
    for row in rows:
        row["created_this_run"] = row["path"] in changed
    result = {"status": "files_found" if rows else "no_dss", "project_dir": str(root), "dss_reading_status": "planned", "files": rows}
    json_path = reports / "hec_hms_dss_discovery.json"
    md_path = reports / "hec_hms_dss_discovery.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# HEC-HMS DSS Discovery", "", f"- Status: `{result['status']}`", "- Deep reading: `planned`", "", "| Path | Size | Empty | Created this run | Role |", "| --- | ---: | --- | --- | --- |"]
    lines.extend(f"| {row['path']} | {row['size_bytes']} | {row['is_empty']} | {row['created_this_run']} | {row['possible_role']} |" for row in rows)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def write_hms_official_validation_summary(output_dir: str | Path = HMS_REFERENCE_ROOT / "reports") -> dict[str, Path]:
    output = _resolve(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    reference_path = output / "hec_hms_official_reference_result.json"
    generated_root = HMS_VERIFIED_ROOT
    open_path = generated_root / "reports" / "hec_hms_open_probe.json"
    compute_path = generated_root / "reports" / "hec_hms_compute_probe.json"
    load = lambda path: json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    reference_result = load(reference_path)
    open_result = load(open_path)
    compute_result = load(compute_path)
    level = classify_hms_validation_level(reference_result, open_result, compute_result)
    summary = {
        "generated_at": _now(),
        "reference_result": reference_result,
        "generated_open_result": open_result,
        "generated_compute_result": compute_result,
        "validation_level": level,
        "dss_reading_status": "planned",
    }
    json_path = output / "hec_hms_official_validation_summary.json"
    md_path = output / "hec_hms_official_validation_summary.md"
    xlsx_path = output / "hec_hms_official_validation_summary.xlsx"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    overview = {
        "validation_level": level,
        "reference_open": (reference_result or {}).get("open_status", "not_run"),
        "reference_compute": (reference_result or {}).get("compute_status", "not_run"),
        "generated_open": (open_result or {}).get("status", "not_run"),
        "generated_compute": (compute_result or {}).get("status", "not_run"),
        "dss_reading_status": "planned",
    }
    pd.DataFrame([overview]).to_excel(xlsx_path, index=False)
    md_path.write_text(
        "\n".join(
            [
                "# HEC-HMS Official Validation Summary",
                "",
                f"- Validation level: `{level}`",
                f"- Reference open: `{overview['reference_open']}`",
                f"- Reference compute: `{overview['reference_compute']}`",
                f"- Generated open: `{overview['generated_open']}`",
                f"- Generated compute: `{overview['generated_compute']}`",
                "- DSS deep reading: `planned`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path, "xlsx": xlsx_path}
