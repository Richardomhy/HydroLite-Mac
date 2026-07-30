from __future__ import annotations

from pathlib import Path
import json
import os
import sys

from hydrolite.desktop.desktop_paths import get_application_support_dir


REQUIRED_RESOURCES = ("streamlit_app.py", "templates", "configs", "docs", "data_demo")


def locate_bundle_root() -> Path:
    if os.getenv("HYDROLITE_BUNDLE_RESOURCES"):
        return Path(os.environ["HYDROLITE_BUNDLE_RESOURCES"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parents[2]


def locate_bundled_resource(path: str | Path) -> Path:
    candidate = (locate_bundle_root() / path).resolve()
    root = locate_bundle_root()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Bundle resource path escapes the read-only resource root")
    return candidate


def locate_writable_application_data() -> Path:
    path = get_application_support_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def detect_missing_resource(path: str | Path) -> dict:
    candidate = locate_bundled_resource(path)
    return {"resource": str(path), "path": str(candidate), "exists": candidate.exists()}


def validate_bundle_resources(root: str | Path | None = None) -> dict:
    base = Path(root).resolve() if root else locate_bundle_root()
    checks = []
    for name in REQUIRED_RESOURCES:
        candidate = base / name
        checks.append({"resource": name, "path": str(candidate), "exists": candidate.exists()})
    missing = [item["resource"] for item in checks if not item["exists"]]
    return {"status": "passed" if not missing else "failed", "root": str(base), "checks": checks, "missing": missing, "bundle_read_only": True}


def write_bundle_resource_report(output_dir: str | Path, result: dict | None = None) -> dict[str, Path]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    result = result or validate_bundle_resources()
    json_path, md_path = output / "bundle_resource_report.json", output / "bundle_resource_report.md"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md_path.write_text("# Bundle Resource Report\n\n" + f"- Status: `{result['status']}`\n- Root: `{result['root']}`\n- Missing: `{', '.join(result['missing']) or 'none'}`\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
