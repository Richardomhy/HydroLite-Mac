from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ALPHA_TAG_COMMIT = "e81f194cbca58c3a88f8176b6da114d6a46ee1c6"
BETA_TAG_COMMIT = "67a386dd0de53ef7c22bdbd054adaf7c5aef122b"
ISSUE_TEMPLATE_DIR = Path(".github/ISSUE_TEMPLATE")
BETA_DOCS = [
    Path("docs/post_release_validation.md"),
    Path("docs/cloud_smoke_test.md"),
    Path("docs/local_smoke_test.md"),
    Path("docs/beta_feedback_workflow.md"),
]


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run_hydrolite(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hydrolite", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def test_issue_templates_exist_and_include_sensitive_data_reminder():
    expected = [
        "bug_report.yml",
        "feature_request.yml",
        "beta_feedback.yml",
        "data_template_issue.yml",
        "config.yml",
    ]
    for name in expected:
        path = ISSUE_TEMPLATE_DIR / name
        assert path.exists(), name
        text = path.read_text(encoding="utf-8")
        assert "HydroLite" in text or name == "config.yml"
        if name != "config.yml":
            assert "敏感" in text or "sensitive" in text.lower() or "credentials" in text.lower()


def test_beta_feedback_docs_exist():
    for path in BETA_DOCS:
        assert path.exists(), path
        text = path.read_text(encoding="utf-8")
        assert "v0.6.0-beta" in text or "Smoke Test" in text or "反馈" in text


def test_beta_info_cli_executes():
    completed = _run_hydrolite("beta", "info")
    assert completed.returncode == 0, completed.stderr
    assert "version: 0.6.0-beta" in completed.stdout
    assert "github_url: https://github.com/Richardomhy/HydroLite-Mac.git" in completed.stdout
    assert "streamlit_url: https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app" in completed.stdout


def test_beta_checklist_cli_executes():
    completed = _run_hydrolite("beta", "checklist")
    assert completed.returncode == 0, completed.stderr
    assert "GitHub Release" in completed.stdout
    assert "Issue tracking" in completed.stdout


def test_beta_smoke_local_cli_executes():
    before = _snapshot_data_raw()
    completed = _run_hydrolite("beta", "smoke-local")
    assert completed.returncode == 0, completed.stderr
    assert "version: 0.6.0-beta" in completed.stdout
    assert "healthcheck_status:" in completed.stdout
    assert "streamlit_app_exists: True" in completed.stdout
    assert _snapshot_data_raw() == before


def test_streamlit_beta_feedback_page_imports_and_navigation_registered():
    import hydrolite.ui.app as app
    import hydrolite.ui.pages.beta_feedback as beta_feedback
    import streamlit_app

    assert callable(beta_feedback.render)
    assert callable(streamlit_app.main)
    assert "Beta 反馈" in app.PAGES


def test_data_raw_not_modified_by_beta_checks():
    before = _snapshot_data_raw()
    assert before
    _run_hydrolite("beta", "info")
    _run_hydrolite("beta", "checklist")
    assert _snapshot_data_raw() == before


def test_no_tracked_secrets_external_or_model_weights():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    assert completed.returncode == 0, completed.stderr
    tracked = completed.stdout.splitlines()
    forbidden_suffixes = (".pt", ".pth", ".ckpt", ".onnx")
    assert not any(path.endswith(forbidden_suffixes) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)


def test_release_tags_not_moved():
    alpha = subprocess.run(["git", "rev-parse", "v0.5.0-alpha.2"], capture_output=True, text=True, check=False)
    beta = subprocess.run(["git", "rev-parse", "v0.6.0-beta"], capture_output=True, text=True, check=False)
    assert alpha.returncode == 0, alpha.stderr
    assert beta.returncode == 0, beta.stderr
    assert alpha.stdout.strip() == ALPHA_TAG_COMMIT
    assert beta.stdout.strip() == BETA_TAG_COMMIT
