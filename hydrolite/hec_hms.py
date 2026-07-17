from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
from typing import Any

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
