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

import pandas as pd

from hydrolite.data_templates import validate_project_input_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_GIS_DIR = PROJECT_ROOT / "data_demo" / "gis"

FIELD_ALIASES = {
    "subbasins": {
        "subbasin_id": ["subbasin_id", "sub_id", "id", "name", "basin_id"],
        "area_km2": ["area_km2", "area", "area_sqkm", "area_km", "Shape_Area"],
        "cn": ["cn", "curve_number", "CN"],
        "initial_abstraction_ratio": ["initial_abstraction_ratio", "ia_ratio", "lambda"],
        "lag_time_hr": ["lag_time_hr", "lag_hr", "lag_time", "tc_hr", "lag_hours"],
        "outlet_reach_id": ["outlet_reach_id", "reach_id", "outlet", "outlet_id"],
    },
    "reaches": {
        "reach_id": ["reach_id", "rid", "id", "name"],
        "upstream_reach_id": ["upstream_reach_id", "upstream", "from_id", "from_node"],
        "downstream_reach_id": ["downstream_reach_id", "downstream", "to_id", "to_node"],
        "length_km": ["length_km", "length", "len_km", "Shape_Length"],
        "slope": ["slope", "slope_m_m", "gradient"],
        "muskingum_k_hr": ["muskingum_k_hr", "k_hr", "K", "k_hours"],
        "muskingum_x": ["muskingum_x", "x", "X"],
    },
}

DEFAULTS = {
    "initial_abstraction_ratio": 0.2,
    "cn": 75,
    "lag_time_hr": 1.0,
    "muskingum_k_hr": 2.0,
    "muskingum_x": 0.2,
}


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


def _geojson_features(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        return [feature for feature in data.get("features", []) if isinstance(feature, dict)]
    if data.get("type") == "Feature":
        return [data]
    return []


def infer_hydrolite_field_mapping(layer_path: str | Path, target_template: str) -> dict[str, Any]:
    features = _geojson_features(layer_path)
    fields = sorted({key for feature in features for key in (feature.get("properties") or {}).keys()})
    aliases = FIELD_ALIASES[target_template]
    mapping: dict[str, str | None] = {}
    warnings: list[str] = []
    lower_lookup = {field.lower(): field for field in fields}
    for target, candidates in aliases.items():
        match = next((lower_lookup[name.lower()] for name in candidates if name.lower() in lower_lookup), None)
        mapping[target] = match
        if match is None:
            warnings.append(f"No source field found for {target}.")
    return {"target_template": target_template, "layer_path": str(layer_path), "source_fields": fields, "mapping": mapping, "warnings": warnings}


def _mapped_rows(layer_path: str | Path, target_template: str, mapping: dict[str, str | None] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    features = _geojson_features(layer_path)
    inferred = infer_hydrolite_field_mapping(layer_path, target_template)
    mapping = mapping or inferred["mapping"]
    warnings = list(inferred["warnings"])
    rows: list[dict[str, Any]] = []
    id_field = "subbasin_id" if target_template == "subbasins" else "reach_id"
    prefix = "SUB" if target_template == "subbasins" else "R"
    targets = list(FIELD_ALIASES[target_template])
    for index, feature in enumerate(features, start=1):
        props = feature.get("properties") or {}
        row: dict[str, Any] = {}
        for target in targets:
            source = mapping.get(target)
            row[target] = props.get(source) if source else DEFAULTS.get(target, "")
        if not row.get(id_field):
            row[id_field] = f"{prefix}{index}"
            warnings.append(f"{id_field} missing for row {index}; generated {row[id_field]}.")
        if target_template == "subbasins":
            if not row.get("area_km2"):
                warnings.append(f"area_km2 missing for {row[id_field]}; left blank.")
            source = mapping.get("area_km2")
            if source and source.lower() == "shape_area" and pd.notna(row["area_km2"]):
                value = float(row["area_km2"])
                if value > 10000:
                    row["area_km2"] = value / 1_000_000
                    warnings.append("Shape_Area appears to be square meters; converted to km2.")
        if target_template == "reaches":
            if not row.get("length_km"):
                warnings.append(f"length_km missing for {row[id_field]}; left blank.")
            source = mapping.get("length_km")
            if source and source.lower() == "shape_length" and pd.notna(row["length_km"]):
                value = float(row["length_km"])
                if value > 1000:
                    row["length_km"] = value / 1000
                    warnings.append("Shape_Length appears to be meters; converted to km.")
        rows.append(row)
    return rows, sorted(set(warnings))


def convert_geojson_to_subbasins_csv(layer_path: str | Path, output_csv: str | Path, mapping: dict[str, str | None] | None = None) -> dict[str, Any]:
    rows, warnings = _mapped_rows(layer_path, "subbasins", mapping)
    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(FIELD_ALIASES["subbasins"])).to_csv(output, index=False)
    return {"status": "success", "output_csv": str(output), "rows": len(rows), "warnings": warnings}


def convert_geojson_to_reaches_csv(layer_path: str | Path, output_csv: str | Path, mapping: dict[str, str | None] | None = None) -> dict[str, Any]:
    rows, warnings = _mapped_rows(layer_path, "reaches", mapping)
    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(FIELD_ALIASES["reaches"])).to_csv(output, index=False)
    return {"status": "success", "output_csv": str(output), "rows": len(rows), "warnings": warnings}


def export_basin_boundary_geojson(layer_path: str | Path, output_geojson: str | Path) -> dict[str, Any]:
    return qgis_export_vector(layer_path, output_geojson, output_format="GeoJSON")


def validate_qgis_to_hydrolite_outputs(output_dir: str | Path) -> dict[str, Any]:
    return validate_project_input_dataset(output_dir)


def write_qgis_to_hydrolite_report(output_dir: str | Path, conversion_result: dict[str, Any]) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    validation = validate_qgis_to_hydrolite_outputs(root)
    report = root / "qgis_to_hydrolite_mapping_report.md"
    summary = root / "qgis_to_hydrolite_summary.xlsx"
    manifest = root / "qgis_to_hydrolite_manifest.json"
    report.write_text(
        "\n".join(
            [
                "# QGIS to HydroLite Input Conversion",
                "",
                f"- status: `{conversion_result.get('status', 'success')}`",
                f"- output_dir: `{root}`",
                f"- validation_status: `{validation['status']}`",
                "",
                "This conversion uses GeoJSON properties and HydroLite data templates. It is not a full QGIS plugin.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(validation["checks"]).to_excel(summary, index=False)
    manifest.write_text(
        json.dumps({"conversion": conversion_result, "validation": validation}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"report": report, "summary": summary, "manifest": manifest}


def convert_qgis_layers_to_hydrolite_inputs(
    subbasins_layer: str | Path,
    reaches_layer: str | Path,
    basin_layer: str | Path,
    output_dir: str | Path,
    mappings: dict[str, dict[str, str | None]] | None = None,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    mappings = mappings or {}
    rainfall = root / "rainfall.csv"
    if not rainfall.exists():
        pd.DataFrame([{"time": "2026-01-01 00:00", "rainfall_mm": 0.0}]).to_csv(rainfall, index=False)
    result = {
        "status": "success",
        "output_dir": str(root),
        "rainfall_placeholder": str(rainfall),
        "subbasins": convert_geojson_to_subbasins_csv(subbasins_layer, root / "subbasins.csv", mappings.get("subbasins")),
        "reaches": convert_geojson_to_reaches_csv(reaches_layer, root / "reaches.csv", mappings.get("reaches")),
        "basin_boundary": export_basin_boundary_geojson(basin_layer, root / "basin_boundary.geojson"),
    }
    result["reports"] = {key: str(path) for key, path in write_qgis_to_hydrolite_report(root, result).items()}
    return result


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
