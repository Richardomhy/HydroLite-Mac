from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import subprocess
import zipfile
from typing import Any

from hydrolite.__version__ import __app_name__, __release_date__, __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = PROJECT_ROOT / "release" / f"v{__version__}"
FORBIDDEN_SUFFIXES = (".pt", ".pth", ".ckpt", ".onnx")
FORBIDDEN_PARTS = ("secrets.toml", "credentials", "service-account", "external/", "data_raw", "checkpoint")


def current_git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return completed.stdout.strip() if completed.returncode == 0 else ""
    except Exception:
        return ""


def release_file_is_safe(path: Path) -> bool:
    text = path.as_posix().lower()
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return False
    return not any(part in text for part in FORBIDDEN_PARTS)


def release_directory_is_safe(release_dir: str | Path = RELEASE_DIR) -> bool:
    root = Path(release_dir)
    if not root.exists():
        return True
    for path in root.rglob("*"):
        if path.is_file() and not release_file_is_safe(path):
            return False
        if path.suffix == ".zip":
            try:
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        lower = name.lower()
                        if lower.endswith(FORBIDDEN_SUFFIXES) or any(part in lower for part in FORBIDDEN_PARTS):
                            return False
            except zipfile.BadZipFile:
                return False
    return True


def build_release_manifest(
    release_dir: str | Path = RELEASE_DIR,
    *,
    test_summary: str = "pytest -q passed",
    warnings: list[str] | None = None,
) -> Path:
    root = Path(release_dir)
    root.mkdir(parents=True, exist_ok=True)
    files = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file() and path.name != "release_manifest.json")
    manifest: dict[str, Any] = {
        "app_name": __app_name__,
        "version": __version__,
        "release_date": __release_date__,
        "git_commit": current_git_commit(),
        "git_tag": f"v{__version__}",
        "github_url": "https://github.com/Richardomhy/HydroLite-Mac.git",
        "streamlit_url": "https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app",
        "included_features": [
            "GitHub Issue templates",
            "Beta feedback Streamlit page",
            "Beta CLI info/checklist/smoke-local",
            "Cloud and local smoke test docs",
            "Post-release validation workflow",
        ],
        "patch_changes": [
            "Promoted beta feedback workflow into v0.6.0-beta.1 patch release.",
            "Kept v0.6.0-beta model algorithms and project workflow unchanged.",
        ],
        "files": files,
        "test_summary": test_summary,
        "warnings": warnings or [
            "This is an alpha release for demonstration and workflow validation.",
            "OpenHydroNet support prepares input packages only; it does not run real AI prediction.",
            "GEE and SWMM backends depend on local/cloud environment availability.",
        ],
        "security_checks": {
            "no_secrets": release_directory_is_safe(root),
            "no_external_repo": release_directory_is_safe(root),
            "no_model_weights": release_directory_is_safe(root),
            "no_checkpoints": release_directory_is_safe(root),
            "no_data_raw": release_directory_is_safe(root),
        },
        "known_limitations": [
            "GEE, SWMM, and OpenHydroNet backends remain optional environment-dependent integrations.",
            "OpenHydroNet support prepares input packages only and does not train or run large inference.",
            "Online Streamlit is for demo and feedback; full workflows are recommended locally.",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = root / "release_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def prepare_release_directory() -> Path:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    copies = {
        PROJECT_ROOT / "projects" / "demo_project" / "reports" / "demo_project_package.zip": RELEASE_DIR / "demo_project_package.zip",
        PROJECT_ROOT / "docs" / "release_notes_v0.5.0-alpha.md": RELEASE_DIR / "release_notes_v0.5.0-alpha.md",
        PROJECT_ROOT / "docs" / "installation_guide.md": RELEASE_DIR / "installation_guide.md",
        PROJECT_ROOT / "docs" / "demo_walkthrough.md": RELEASE_DIR / "demo_walkthrough.md",
        PROJECT_ROOT / "docs" / "known_limitations.md": RELEASE_DIR / "known_limitations.md",
    }
    for source, target in copies.items():
        if source.exists():
            shutil.copy2(source, target)
    build_release_manifest(RELEASE_DIR, test_summary="pending; run pytest -q before publishing")
    return RELEASE_DIR
