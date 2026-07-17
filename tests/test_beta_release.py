from __future__ import annotations

from pathlib import Path
import json
import subprocess
import zipfile

from hydrolite.__version__ import __version__


RELEASE_DIR = Path("release/v0.6.0-beta.1")
ALPHA_TAG_COMMIT = "e81f194cbca58c3a88f8176b6da114d6a46ee1c6"
BETA_TAG_COMMIT = "67a386dd0de53ef7c22bdbd054adaf7c5aef122b"


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _unsafe_name(name: str) -> bool:
    lowered = name.lower()
    return (
        "secret" in lowered
        or "credential" in lowered
        or "service-account" in lowered
        or lowered.startswith("external/")
        or lowered.startswith("data_raw/")
        or lowered.endswith((".pt", ".pth", ".ckpt", ".onnx"))
    )


def test_beta_version():
    assert __version__ == "0.7.0-dev"


def test_beta_release_files_exist_and_manifest_readable():
    assert RELEASE_DIR.exists()
    assert Path("docs/release_notes_v0.6.0-beta.1.md").exists()
    manifest = RELEASE_DIR / "release_manifest.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["app_name"] == "HydroLite Studio"
    assert data["version"] == "0.6.0-beta.1"
    assert data["git_tag"] == "v0.6.0-beta.1"


def test_beta_release_bundles_exist_and_are_safe():
    for name in ("data_templates_bundle.zip", "demo_project_package.zip", "project_report_bundle.zip"):
        path = RELEASE_DIR / name
        assert path.exists()
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        assert names
        assert not any(_unsafe_name(item) for item in names)


def test_beta_release_directory_has_no_forbidden_files():
    for path in RELEASE_DIR.rglob("*"):
        if path.is_file():
            rel = path.relative_to(RELEASE_DIR).as_posix()
            assert not _unsafe_name(rel)


def test_readme_and_streamlit_import():
    assert Path("README.md").read_text(encoding="utf-8")
    import streamlit_app
    import hydrolite.ui.app as app

    assert callable(streamlit_app.main)
    assert "数据模板" in app.PAGES
    assert "教程与 Demo" in app.PAGES


def test_data_raw_not_modified_by_release_checks():
    before = _snapshot_data_raw()
    assert before
    assert _snapshot_data_raw() == before


def test_alpha_tag_not_moved():
    completed = subprocess.run(
        ["git", "rev-parse", "v0.5.0-alpha.2"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ALPHA_TAG_COMMIT


def test_beta_tag_not_moved():
    completed = subprocess.run(
        ["git", "rev-parse", "v0.6.0-beta"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == BETA_TAG_COMMIT
