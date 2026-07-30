from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import json
import locale
import os
import platform
import subprocess
import sys
import time
import uuid

from hydrolite.__version__ import __version__
from hydrolite.connectors import list_connectors
from hydrolite.runtime_db import create_environment_record
from hydrolite.runtime_mode import detect_runtime_mode


def capture_python_environment() -> dict:
    return {"version": sys.version, "executable": sys.executable, "prefix": sys.prefix}


def capture_conda_environment() -> dict:
    return {"prefix": os.getenv("CONDA_PREFIX", ""), "default_env": os.getenv("CONDA_DEFAULT_ENV", ""), "detected": bool(os.getenv("CONDA_PREFIX"))}


def capture_pip_packages() -> list[dict]:
    packages = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            packages.append({"name": name, "version": dist.version})
    return sorted(packages, key=lambda row: row["name"].casefold())


def capture_optional_dependencies() -> dict:
    names = ("psutil", "rasterio", "geopandas", "earthaccess", "cdsapi", "pystac-client", "pyswmm", "swmm-toolkit")
    result = {}
    for name in names:
        try:
            result[name] = {"available": True, "version": metadata.version(name)}
        except metadata.PackageNotFoundError:
            result[name] = {"available": False, "version": ""}
    return result


def capture_system_information() -> dict:
    return {"platform": platform.platform(), "system": platform.system(), "release": platform.release(), "machine": platform.machine(), "timezone": time.tzname, "locale": locale.getlocale()}


def capture_qgis_information() -> dict:
    candidates = [Path("/Applications/QGIS.app"), Path("/Applications/QGIS-LTR.app")]
    return {"detected": any(path.exists() for path in candidates), "applications": [str(path) for path in candidates if path.exists()]}


def capture_hec_hms_information() -> dict:
    applications = sorted(Path("/Applications").glob("HEC-HMS*.app")) if Path("/Applications").exists() else []
    return {"detected": bool(applications), "applications": [str(path) for path in applications]}


def capture_git_information(repo_dir: str | Path) -> dict:
    root = Path(repo_dir).resolve()
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False, timeout=10).stdout.strip()
    return {"commit": run("rev-parse", "HEAD"), "branch": run("branch", "--show-current"), "dirty": bool(run("status", "--porcelain"))}


def capture_connector_status() -> list[dict]:
    rows = list_connectors()
    for row in rows:
        authentication = row.get("authentication", {})
        if isinstance(authentication, dict):
            row["authentication"] = {key: value for key, value in authentication.items() if not any(word in key.lower() for word in ("token", "password", "key", "secret"))}
    return rows


def capture_environment(repo_dir: str | Path | None = None) -> dict:
    repo = Path(repo_dir or Path(__file__).resolve().parents[1])
    result = {
        "environment_id": f"env_{uuid.uuid4().hex[:12]}",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "hydrolite_version": __version__,
        "python": capture_python_environment(),
        "conda": capture_conda_environment(),
        "pip_packages": capture_pip_packages(),
        "system": capture_system_information(),
        "optional_dependencies": capture_optional_dependencies(),
        "qgis": capture_qgis_information(),
        "hec_hms": capture_hec_hms_information(),
        "git": capture_git_information(repo),
        "connectors": capture_connector_status(),
        "runtime_mode": detect_runtime_mode(),
    }
    create_environment_record(result["environment_id"], result)
    return result


def write_environment_snapshot(output_dir: str | Path, result: dict) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    json_path = output / "environment_snapshot.json"
    md_path = output / "environment_snapshot.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(
        "# Environment Snapshot\n\n"
        f"- HydroLite: `{result['hydrolite_version']}`\n"
        f"- Python: `{result['python']['executable']}`\n"
        f"- Runtime mode: `{result['runtime_mode']['mode']}`\n"
        f"- Git commit: `{result['git']['commit']}`\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path}


def compare_environment_snapshots(left: str | Path | dict, right: str | Path | dict) -> dict:
    def load(value):
        return json.loads(Path(value).read_text(encoding="utf-8")) if not isinstance(value, dict) else value
    a, b = load(left), load(right)
    keys = ("hydrolite_version", "python", "conda", "system", "optional_dependencies", "runtime_mode")
    differences = {key: {"left": a.get(key), "right": b.get(key)} for key in keys if a.get(key) != b.get(key)}
    return {"status": "same" if not differences else "different", "differences": differences}
