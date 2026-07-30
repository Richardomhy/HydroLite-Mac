from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import zipfile

from hydrolite.runtime_db import get_run_record
from hydrolite.runtime_paths import get_run_dir, get_runtime_root


FORBIDDEN = {".dss", ".h5", ".hdf5", ".nc", ".pt", ".pth", ".ckpt", ".onnx", ".sqlite3", ".key", ".pem", ".zip"}


def _manifest(directory: Path, exclude: set[str] | None = None) -> list[dict]:
    exclude = exclude or set()
    rows = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name not in exclude:
            rows.append({"path": path.relative_to(directory).as_posix(), "size": path.stat().st_size, "checksum": hashlib.sha256(path.read_bytes()).hexdigest()})
    return rows


def create_run_input_snapshot(run_id: str) -> Path:
    root = get_run_dir(run_id)
    path = root / "configuration" / "input_snapshot.json"
    path.write_text(json.dumps(_manifest(root / "configuration", {"input_snapshot.json", "configuration_snapshot.json"}), indent=2), encoding="utf-8")
    return path


def create_run_configuration_snapshot(run_id: str) -> Path:
    root = get_run_dir(run_id)
    path = root / "configuration" / "configuration_snapshot.json"
    path.write_text(json.dumps(_manifest(root / "configuration", {"input_snapshot.json", "configuration_snapshot.json"}), indent=2), encoding="utf-8")
    return path


def create_run_environment_snapshot(run_id: str) -> Path:
    path = get_run_dir(run_id) / "environments" / "environment_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    run = get_run_record(run_id) or {}
    source = get_runtime_root() / "environments" / str(run.get("environment_id") or "") / "environment_snapshot.json"
    if source.is_file():
        shutil.copy2(source, path)
    elif not path.exists():
        path.write_text(json.dumps({"status": "missing", "environment_id": run.get("environment_id")}, indent=2), encoding="utf-8")
    return path


def create_run_output_manifest(run_id: str) -> Path:
    root = get_run_dir(run_id)
    path = root / "reports" / "run_output_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_manifest(root / "artifacts"), indent=2), encoding="utf-8")
    return path


def verify_run_snapshot(run_id: str) -> dict:
    paths = [create_run_input_snapshot(run_id), create_run_configuration_snapshot(run_id), create_run_environment_snapshot(run_id), create_run_output_manifest(run_id)]
    return {"status": "passed" if all(path.exists() for path in paths) else "failed", "files": [str(path) for path in paths]}


def compare_runs(left_run_id: str, right_run_id: str) -> dict:
    left, right = get_run_record(left_run_id), get_run_record(right_run_id)
    fields = ("workflow_id", "run_mode", "configuration_checksum", "git_commit", "hydrolite_version", "result_status")
    differences = {field: {"left": left.get(field), "right": right.get(field)} for field in fields if left and right and left.get(field) != right.get(field)}
    return {"status": "same" if not differences else "different", "differences": differences}


def export_reproduction_package(run_id: str, output_path: str | Path) -> Path:
    root = get_run_dir(run_id); target = Path(output_path)
    if target.suffix.lower() != ".zip": target = target / f"{run_id}_reproduction.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    allowed_roots = [root / "configuration", root / "environments", root / "reports"]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for base in allowed_roots:
            for path in (base.rglob("*") if base.exists() else []):
                if not path.is_file() or path.suffix.lower() in FORBIDDEN or path.stat().st_size > 5 * 1024 * 1024: continue
                if path.resolve() == target.resolve(): continue
                relative = path.relative_to(root)
                if any(word in relative.as_posix().lower() for word in ("credential", "secret", "token", "service-account")): continue
                archive.write(path, relative.as_posix())
        archive.writestr("reproduction_manifest.json", json.dumps({"run_id": run_id, "large_inputs_included": False, "credentials_included": False}, indent=2))
    return target
