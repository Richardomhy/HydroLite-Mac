from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile


APP_NAME = "HydroLite Studio"


def get_application_support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def get_desktop_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / APP_NAME


def get_desktop_cache_dir() -> Path:
    return Path.home() / "Library" / "Caches" / APP_NAME


def get_desktop_preferences_dir() -> Path:
    return Path.home() / "Library" / "Preferences"


def get_desktop_temp_dir() -> Path:
    return Path(tempfile.gettempdir()) / APP_NAME


def ensure_desktop_directories() -> dict[str, Path]:
    paths = {
        "application_support": get_application_support_dir(),
        "logs": get_desktop_log_dir(),
        "cache": get_desktop_cache_dir(),
        "preferences": get_desktop_preferences_dir(),
        "temp": get_desktop_temp_dir(),
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def detect_legacy_runtime() -> dict:
    path = Path(os.getenv("HYDROLITE_LEGACY_RUNTIME", "~/.hydrolite")).expanduser().resolve()
    return {"detected": path.exists(), "path": str(path), "size_bytes": _tree_size(path)}


def plan_legacy_runtime_migration() -> dict:
    legacy = Path(detect_legacy_runtime()["path"])
    target = get_application_support_dir() / "legacy_runtime"
    required = _tree_size(legacy)
    free = shutil.disk_usage(target.parent if target.parent.exists() else Path.home()).free
    return {
        "status": "ready" if legacy.exists() and free > required * 2 else "not_required" if not legacy.exists() else "insufficient_space",
        "source": str(legacy),
        "target": str(target),
        "backup": str(get_application_support_dir() / "migration_backups" / "legacy_runtime"),
        "required_bytes": required,
        "free_bytes": free,
        "execute_default": False,
    }


def execute_legacy_runtime_migration(execute: bool = False) -> dict:
    plan = plan_legacy_runtime_migration()
    if not execute:
        return {**plan, "status": "dry_run"}
    if plan["status"] != "ready":
        return plan
    source, target, backup = map(Path, (plan["source"], plan["target"], plan["backup"]))
    if target.exists():
        raise FileExistsError(f"Migration target already exists: {target}")
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copytree(source, backup)
    shutil.copytree(source, target)
    manifest = {"source_checksum": _tree_checksum(source), "target_checksum": _tree_checksum(target)}
    (target.parent / "legacy_migration.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "copied", **plan, **manifest}


def validate_migration() -> dict:
    source = Path(detect_legacy_runtime()["path"])
    target = get_application_support_dir() / "legacy_runtime"
    valid = source.exists() and target.exists() and _tree_checksum(source) == _tree_checksum(target)
    return {"status": "passed" if valid else "not_migrated", "source": str(source), "target": str(target)}


def rollback_migration() -> dict:
    target = get_application_support_dir() / "legacy_runtime"
    if target.exists():
        shutil.rmtree(target)
    return {"status": "rolled_back", "original_legacy_runtime_preserved": True}


def _tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.exists() else 0


def _tree_checksum(root: Path) -> str:
    digest = hashlib.sha256()
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
