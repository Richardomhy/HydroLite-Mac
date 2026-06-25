from __future__ import annotations

from pathlib import Path
import json
import os
import platform
import shutil
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
