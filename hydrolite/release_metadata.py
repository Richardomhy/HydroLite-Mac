from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import re
import subprocess

from hydrolite.__version__ import __app_name__, __release_date__, __version__


def load_version() -> dict:
    base = __version__.split("-", 1)[0]
    channel = "dev" if "dev" in __version__ else "beta" if "beta" in __version__ else "alpha" if "alpha" in __version__ else "stable"
    return {"app_name": __app_name__, "version": __version__, "short_version": base, "release_date": __release_date__, "channel": channel}


def validate_release_version(version: str | None = None) -> dict:
    value = version or __version__
    valid = bool(re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:dev|alpha|beta)(?:\.\d+)?)?", value))
    return {"status": "passed" if valid else "failed", "version": value}


def calculate_build_number(repo_dir: str | Path | None = None) -> int:
    root = Path(repo_dir or Path(__file__).resolve().parents[1])
    result = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root, capture_output=True, text=True, check=False, timeout=10)
    return max(1, int(result.stdout.strip() or 1))


def build_release_manifest(**overrides) -> dict:
    info = load_version()
    manifest = {
        **info, "bundle_id": "com.hydrolite.studio", "build_number": calculate_build_number(),
        "architecture": "arm64", "distribution_level": "local_ad_hoc_app",
        "code_signing": {"mode": "ad_hoc", "developer_id": False},
        "notarization": {"status": "credentials_required"},
        "update_readiness": "framework_ready_configuration_missing",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest.update(overrides)
    return manifest


def validate_release_manifest(manifest: dict) -> dict:
    required = {"app_name", "version", "short_version", "bundle_id", "build_number", "architecture", "distribution_level"}
    missing = sorted(required - set(manifest))
    errors = [f"missing {name}" for name in missing]
    if int(manifest.get("build_number", 0)) <= 0:
        errors.append("build_number must be positive")
    return {"status": "passed" if not errors else "failed", "errors": errors}


def compare_release_versions(left: str, right: str) -> int:
    def parts(value: str):
        return tuple(int(item) for item in re.findall(r"\d+", value)[:3])
    return (parts(left) > parts(right)) - (parts(left) < parts(right))


def write_release_metadata(output_dir: str | Path, manifest: dict | None = None) -> Path:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    path = output / "release_manifest.json"
    path.write_text(json.dumps(manifest or build_release_manifest(), indent=2), encoding="utf-8")
    return path
