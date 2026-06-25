from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ALPHA_TAG_COMMIT = "e81f194cbca58c3a88f8176b6da114d6a46ee1c6"
BETA_TAG_COMMIT = "67a386dd0de53ef7c22bdbd054adaf7c5aef122b"
BETA_1_TAG_COMMIT = "616fa6754b73b64d222ad508c1ab57bb52364365"


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(Path("data_raw").rglob("*"))
        if path.is_file()
    }


def test_roadmap_docs_exist():
    for path in (
        "docs/roadmap_v0.7.0.md",
        "docs/milestones_v0.7.0.md",
        "docs/issue_backlog_v0.7.0.md",
        "docs/qgis_bridge_roadmap.md",
        "docs/calibration_roadmap.md",
        "docs/desktop_app_roadmap.md",
    ):
        text = Path(path).read_text(encoding="utf-8")
        assert "v0.7.0" in text or "Roadmap" in text


def test_roadmap_cli_executes():
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "roadmap"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "current_stable_version: 0.6.0-beta.1" in completed.stdout
    assert "roadmap_v0.7.0.md" in completed.stdout
    assert "milestones_v0.7.0.md" in completed.stdout
    assert "issue_backlog_v0.7.0.md" in completed.stdout


def test_readme_mentions_v070_planning():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "docs/roadmap_v0.7.0.md" in text
    assert "planning only" in text


def test_roadmap_checks_do_not_modify_data_raw():
    before = _snapshot_data_raw()
    assert before
    subprocess.run([sys.executable, "-m", "hydrolite", "roadmap"], check=False, capture_output=True, text=True)
    assert _snapshot_data_raw() == before


def test_no_tracked_secrets_external_or_model_weights_for_roadmap():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    assert completed.returncode == 0, completed.stderr
    tracked = completed.stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)


def test_release_tags_not_moved_for_roadmap():
    expected = {
        "v0.5.0-alpha.2": ALPHA_TAG_COMMIT,
        "v0.6.0-beta": BETA_TAG_COMMIT,
        "v0.6.0-beta.1": BETA_1_TAG_COMMIT,
    }
    for tag, commit in expected.items():
        completed = subprocess.run(["git", "rev-parse", tag], capture_output=True, text=True, check=False, timeout=60)
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == commit
