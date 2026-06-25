from __future__ import annotations

from pathlib import Path
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_GIS_DIR = PROJECT_ROOT / "data_demo" / "gis"


def _unique(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def detect_qgis_app_paths() -> dict[str, Any]:
    apps = _unique(
        [
            Path("/Applications/QGIS.app"),
            Path("/Applications/QGIS-LTR.app"),
            *Path("/Applications").glob("*QGIS*.app"),
        ]
    )
    return {
        "qgis_app_exists": Path("/Applications/QGIS.app").exists(),
        "qgis_ltr_app_exists": Path("/Applications/QGIS-LTR.app").exists(),
        "qgis_apps": [{"path": str(path), "exists": path.exists()} for path in apps],
    }


def detect_qgis_process_candidates() -> list[dict[str, Any]]:
    which = shutil.which("qgis_process")
    paths = [
        Path(which) if which else None,
        Path("/Applications/QGIS.app/Contents/MacOS/bin/qgis_process"),
        Path("/Applications/QGIS.app/Contents/MacOS/qgis_process"),
        Path("/Applications/QGIS-LTR.app/Contents/MacOS/bin/qgis_process"),
        Path("/Applications/QGIS-LTR.app/Contents/MacOS/qgis_process"),
        *Path("/Applications").glob("QGIS*.app/Contents/MacOS/bin/qgis_process"),
        *Path("/Applications").glob("QGIS*.app/Contents/MacOS/qgis_process"),
        Path("/opt/homebrew/bin/qgis_process"),
        Path("/usr/local/bin/qgis_process"),
    ]
    return [
        {"path": str(path), "exists": path.exists(), "executable": os.access(path, os.X_OK)}
        for path in _unique([path for path in paths if path is not None])
    ]


def get_qgis_process_path() -> str | None:
    for item in detect_qgis_process_candidates():
        if item["exists"] and item["executable"]:
            return item["path"]
    return None


def run_qgis_process(args: list[str], timeout: int = 60) -> dict[str, Any]:
    path = get_qgis_process_path()
    if not path:
        return {"available": False, "return_code": None, "stdout": "", "stderr": "qgis_process not found", "command": args}
    try:
        completed = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "available": True,
            "path": path,
            "command": [path, *args],
            "return_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": True, "path": path, "command": [path, *args], "return_code": None, "stdout": "", "stderr": str(exc)}


def qgis_process_version() -> dict[str, Any]:
    return run_qgis_process(["--version"], timeout=20)


def qgis_process_plugins() -> dict[str, Any]:
    return run_qgis_process(["plugins"], timeout=30)


def qgis_process_algorithms(filter_text: str | None = None) -> dict[str, Any]:
    result = run_qgis_process(["list"], timeout=60)
    lines = result.get("stdout", "").splitlines()
    if filter_text:
        lowered = filter_text.lower()
        lines = [line for line in lines if lowered in line.lower()]
    result["algorithms"] = lines
    return result


def _geojson_layer_info(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features", []) if data.get("type") == "FeatureCollection" else []
    fields = sorted({key for feature in features for key in (feature.get("properties") or {}).keys()})
    geometries = [feature.get("geometry") or {} for feature in features]
    geometry_types = sorted({geometry.get("type", "") for geometry in geometries if geometry})
    coords: list[tuple[float, float]] = []

    def collect(value: Any) -> None:
        if isinstance(value, list) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            coords.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for geometry in geometries:
        collect(geometry.get("coordinates"))
    bounds = None
    if coords:
        xs = [x for x, _ in coords]
        ys = [y for _, y in coords]
        bounds = [min(xs), min(ys), max(xs), max(ys)]
    return {
        "qgis_recognized": True,
        "crs": (data.get("crs") or {}).get("properties", {}).get("name", "EPSG:4326"),
        "geometry_type": ",".join(geometry_types),
        "feature_count": len(features),
        "fields": fields,
        "bounds": bounds,
    }


def qgis_layer_info(input_path: str | Path) -> dict[str, Any]:
    path = Path(input_path)
    info: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "file_type": path.suffix.lower().lstrip("."),
        "crs": None,
        "geometry_type": None,
        "feature_count": None,
        "fields": [],
        "bounds": None,
        "qgis_recognized": False,
        "warnings": [],
        "errors": [],
    }
    if not path.exists():
        info["errors"].append("input file does not exist")
        return info
    if path.suffix.lower() in {".geojson", ".json"}:
        try:
            info.update(_geojson_layer_info(path))
        except Exception as exc:  # noqa: BLE001
            info["errors"].append(f"GeoJSON parse failed: {exc}")
    else:
        info["qgis_recognized"] = get_qgis_process_path() is not None
        info["warnings"].append("Detailed metadata currently uses GeoJSON parser; non-GeoJSON requires QGIS/OGR expansion later.")
    if get_qgis_process_path() is None:
        info["warnings"].append("qgis_process not available; used lightweight file parser only.")
    return info


def qgis_validate_vector_layer(input_path: str | Path) -> dict[str, Any]:
    info = qgis_layer_info(input_path)
    status = "passed" if info["exists"] and info["qgis_recognized"] and not info["errors"] else "warning"
    return {"status": status, "layer_info": info}


def qgis_export_vector(input_path: str | Path, output_path: str | Path, output_format: str = "GeoJSON") -> dict[str, Any]:
    source = Path(input_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = {"status": "warning", "input_path": str(source), "output_path": str(target), "method": "", "message": ""}
    if not source.exists():
        result["message"] = "input file does not exist"
        return result
    if get_qgis_process_path():
        qgis_result = run_qgis_process(["run", "native:savefeatures", "--", f"INPUT={source}", f"OUTPUT={target}"], timeout=60)
        if qgis_result.get("return_code") == 0 and target.exists():
            result.update({"status": "success", "method": "qgis_process:native:savefeatures", "message": qgis_result.get("stdout", "")})
            return result
        result["message"] = qgis_result.get("stderr") or qgis_result.get("stdout") or "qgis_process export failed"
    if source.suffix.lower() in {".geojson", ".json"} and output_format.lower() == "geojson":
        target.write_text(json.dumps(json.loads(source.read_text(encoding="utf-8")), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result.update({"status": "success", "method": "python_geojson_copy", "message": "qgis_process unavailable or failed; copied valid GeoJSON."})
    return result


def qgis_export_attributes_csv(input_path: str | Path, output_csv: str | Path) -> dict[str, Any]:
    source = Path(input_path)
    target = Path(output_csv)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = {"status": "warning", "input_path": str(source), "output_csv": str(target), "method": "", "message": ""}
    if not source.exists():
        result["message"] = "input file does not exist"
        return result
    if source.suffix.lower() not in {".geojson", ".json"}:
        result["message"] = "CSV fallback currently supports GeoJSON properties only."
        return result
    data = json.loads(source.read_text(encoding="utf-8"))
    rows = [(feature.get("properties") or {}) for feature in data.get("features", [])]
    fields = sorted({key for row in rows for key in row.keys()})
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    result.update({"status": "success", "method": "python_geojson_properties", "message": f"wrote {len(rows)} rows"})
    return result


def qgis_bridge_demo(output_dir: str | Path = "output/qgis_bridge_demo") -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    source = DEMO_GIS_DIR / "demo_subbasins.geojson"
    export_geojson = root / "demo_subbasins_export.geojson"
    export_csv = root / "demo_subbasins_attributes.csv"
    summary_path = root / "qgis_bridge_demo_summary.json"
    report_path = root / "qgis_bridge_demo_report.md"
    summary = {
        "qgis_process_version": qgis_process_version(),
        "algorithms_preview": qgis_process_algorithms("save")["algorithms"][:20],
        "layer_info": qgis_layer_info(source),
        "validation": qgis_validate_vector_layer(source),
        "export_vector": qgis_export_vector(source, export_geojson),
        "export_csv": qgis_export_attributes_csv(source, export_csv),
        "outputs": {
            "report": str(report_path),
            "summary": str(summary_path),
            "export_geojson": str(export_geojson),
            "export_csv": str(export_csv),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(
        "\n".join(
            [
                "# QGIS Process Bridge Demo",
                "",
                f"- qgis_process: `{summary['qgis_process_version'].get('path') or 'not found'}`",
                f"- layer: `{source}`",
                f"- validation: `{summary['validation']['status']}`",
                f"- feature_count: `{summary['layer_info'].get('feature_count')}`",
                f"- export_geojson: `{export_geojson}`",
                f"- export_csv: `{export_csv}`",
                "",
                "This is a qgis_process bridge MVP, not a full QGIS plugin.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def detect_qgis_python_candidates() -> list[dict[str, Any]]:
    paths = [
        Path("/Applications/QGIS.app/Contents/MacOS/bin/python3"),
        Path("/Applications/QGIS.app/Contents/MacOS/bin/python"),
        Path("/Applications/QGIS-LTR.app/Contents/MacOS/bin/python3"),
        Path("/Applications/QGIS-LTR.app/Contents/MacOS/bin/python"),
        *Path("/Applications").glob("QGIS*.app/Contents/MacOS/bin/python3"),
        *Path("/Applications").glob("QGIS*.app/Contents/MacOS/bin/python"),
        Path(sys.executable),
    ]
    return [
        {"path": str(path), "exists": path.exists(), "executable": os.access(path, os.X_OK)}
        for path in _unique(paths)
    ]


def run_qgis_process_version(candidate: str | Path | None = None) -> dict[str, Any]:
    candidates = [candidate] if candidate else [
        item["path"] for item in detect_qgis_process_candidates() if item["exists"] and item["executable"]
    ]
    for path in candidates:
        if not path:
            continue
        try:
            completed = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            return {
                "path": str(path),
                "available": completed.returncode == 0,
                "return_code": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"path": str(path), "available": False, "return_code": None, "stdout": "", "stderr": str(exc)}
    return {"path": None, "available": False, "return_code": None, "stdout": "", "stderr": "qgis_process not found"}


def detect_pyqgis_import(candidate_python: str | Path | None = None) -> dict[str, Any]:
    python = str(candidate_python or sys.executable)
    code = "import qgis, PyQt5; from qgis.core import QgsApplication; print('pyqgis_import_ok')"
    try:
        completed = subprocess.run(
            [python, "-c", code],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        return {
            "python": python,
            "can_import_qgis": completed.returncode == 0,
            "can_import_pyqt5": completed.returncode == 0,
            "minimal_check": completed.returncode == 0,
            "return_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "python": python,
            "can_import_qgis": False,
            "can_import_pyqt5": False,
            "minimal_check": False,
            "return_code": None,
            "stdout": "",
            "stderr": str(exc),
        }


def recommend_qgis_bridge_mode(diagnosis: dict[str, Any]) -> dict[str, str]:
    process = diagnosis.get("qgis_process_version", {})
    pyqgis = diagnosis.get("pyqgis_import", {})
    if process.get("available"):
        return {"mode": "qgis_process", "reason": "qgis_process is executable and reports a version."}
    if pyqgis.get("minimal_check"):
        return {"mode": "PyQGIS", "reason": "PyQGIS imports in a candidate Python environment."}
    if diagnosis.get("qgis_apps", {}).get("qgis_apps"):
        return {"mode": "QGIS plugin", "reason": "QGIS app exists, but command-line/PyQGIS bridge is not ready."}
    return {"mode": "暂不可用", "reason": "No usable qgis_process or PyQGIS environment was detected."}


def build_qgis_diagnosis() -> dict[str, Any]:
    apps = detect_qgis_app_paths()
    qgis_process_version = run_qgis_process_version()
    py_candidates = detect_qgis_python_candidates()
    pyqgis = next(
        (
            result
            for result in (detect_pyqgis_import(item["path"]) for item in py_candidates if item["exists"] and item["executable"])
            if result["minimal_check"]
        ),
        detect_pyqgis_import(sys.executable),
    )
    diagnosis: dict[str, Any] = {
        "status": "available" if qgis_process_version["available"] or pyqgis["minimal_check"] else "warning",
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "conda_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        "cwd": str(Path.cwd()),
        "qgis_apps": apps,
        "qgis_process_candidates": detect_qgis_process_candidates(),
        "qgis_process_version": qgis_process_version,
        "qgis_python_candidates": py_candidates,
        "pyqgis_import": pyqgis,
        "next_steps": [],
    }
    diagnosis["recommendation"] = recommend_qgis_bridge_mode(diagnosis)
    if diagnosis["status"] == "warning":
        diagnosis["next_steps"] = [
            "当前环境未检测到可用 QGIS Bridge，可先使用 HydroLite 独立工作流。",
            "如需后续 QGIS 集成，可安装或修复 QGIS-LTR 后重新运行 python -m hydrolite qgis diagnose。",
        ]
    return diagnosis


def _diagnosis_markdown(diagnosis: dict[str, Any]) -> str:
    version = diagnosis["qgis_process_version"]
    pyqgis = diagnosis["pyqgis_import"]
    recommendation = diagnosis["recommendation"]
    lines = [
        "# QGIS Bridge Diagnosis",
        "",
        f"- status: `{diagnosis['status']}`",
        f"- os: `{diagnosis['os']}`",
        f"- python: `{diagnosis['python']}`",
        f"- conda_env: `{diagnosis['conda_env'] or 'none'}`",
        f"- cwd: `{diagnosis['cwd']}`",
        f"- /Applications/QGIS.app: `{diagnosis['qgis_apps']['qgis_app_exists']}`",
        f"- /Applications/QGIS-LTR.app: `{diagnosis['qgis_apps']['qgis_ltr_app_exists']}`",
        f"- qgis_process: `{version.get('path') or 'not found'}`",
        f"- qgis_process --version: `{version.get('stdout') or version.get('stderr') or 'unavailable'}`",
        f"- PyQGIS import: `{pyqgis.get('minimal_check')}`",
        f"- recommendation: `{recommendation['mode']}` - {recommendation['reason']}",
        "",
        "## qgis_process candidates",
    ]
    for item in diagnosis["qgis_process_candidates"]:
        lines.append(f"- `{item['path']}` exists={item['exists']} executable={item['executable']}")
    lines.extend(["", "## QGIS Python candidates"])
    for item in diagnosis["qgis_python_candidates"]:
        lines.append(f"- `{item['path']}` exists={item['exists']} executable={item['executable']}")
    if diagnosis["next_steps"]:
        lines.extend(["", "## Next steps"])
        lines.extend(f"- {step}" for step in diagnosis["next_steps"])
    return "\n".join(lines) + "\n"


def write_qgis_diagnosis(output_dir: str | Path = "output/qgis") -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    diagnosis = build_qgis_diagnosis()
    json_path = root / "qgis_diagnosis.json"
    md_path = root / "qgis_diagnosis.md"
    json_path.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_diagnosis_markdown(diagnosis), encoding="utf-8")
    return {"json": json_path, "md": md_path}
