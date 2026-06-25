from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import zipfile


RELEASE_DIR = Path("release/v0.6.0-beta.1")
ALPHA_TAG_COMMIT = "e81f194cbca58c3a88f8176b6da114d6a46ee1c6"
BETA_TAG_COMMIT = "67a386dd0de53ef7c22bdbd054adaf7c5aef122b"


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
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
        or "checkpoint" in lowered
    )


def test_patch_version():
    from hydrolite.__version__ import __version__

    assert __version__ == "0.6.0-beta.1"


def test_patch_release_directory_and_manifest():
    manifest = RELEASE_DIR / "release_manifest.json"
    assert RELEASE_DIR.exists()
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["app_name"] == "HydroLite Studio"
    assert data["version"] == "0.6.0-beta.1"
    assert data["git_tag"] == "v0.6.0-beta.1"
    for key in ("github_url", "streamlit_url", "included_features", "patch_changes", "security_checks"):
        assert key in data


def test_patch_release_notes_and_issue_templates_exist():
    assert Path("docs/release_notes_v0.6.0-beta.1.md").exists()
    assert Path("docs/release_announcement_v0.6.0-beta.1.md").exists()
    assert Path("docs/v0.6.0_beta_1_checklist.md").exists()
    for name in ("bug_report.yml", "feature_request.yml", "beta_feedback.yml", "data_template_issue.yml"):
        assert (Path(".github/ISSUE_TEMPLATE") / name).exists()


def test_patch_beta_cli_executes():
    for command in (("beta", "info"), ("beta", "checklist"), ("beta", "smoke-local")):
        completed = subprocess.run(
            [sys.executable, "-m", "hydrolite", *command],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert completed.returncode == 0, completed.stderr


def test_patch_release_packages_are_safe():
    for name in ("data_templates_bundle.zip", "demo_project_package.zip", "project_report_bundle.zip"):
        path = RELEASE_DIR / name
        assert path.exists(), name
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        assert names
        assert not any(_unsafe_name(item) for item in names)


def test_patch_streamlit_imports():
    import hydrolite.ui.app as app
    import streamlit_app

    assert callable(app.main)
    assert callable(streamlit_app.main)
    assert "Beta 反馈" in app.PAGES


def test_patch_checks_do_not_modify_data_raw():
    before = _snapshot_data_raw()
    assert before
    subprocess.run([sys.executable, "-m", "hydrolite", "beta", "info"], check=False, capture_output=True, text=True)
    assert _snapshot_data_raw() == before


def test_base_tags_not_moved():
    alpha = subprocess.run(["git", "rev-parse", "v0.5.0-alpha.2"], capture_output=True, text=True, check=False)
    beta = subprocess.run(["git", "rev-parse", "v0.6.0-beta"], capture_output=True, text=True, check=False)
    assert alpha.returncode == 0, alpha.stderr
    assert beta.returncode == 0, beta.stderr
    assert alpha.stdout.strip() == ALPHA_TAG_COMMIT
    assert beta.stdout.strip() == BETA_TAG_COMMIT
