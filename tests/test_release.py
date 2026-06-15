from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_version_imports():
    from hydrolite import __version__
    from hydrolite.__version__ import __app_name__, __release_date__

    assert __version__ == "0.6.0-dev"
    assert __app_name__ == "HydroLite Studio"
    assert __release_date__ == "2026-06-15"


def test_version_cli_executes():
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "HydroLite Studio" in completed.stdout
    assert "0.6.0-dev" in completed.stdout


def test_healthcheck_cli_generates_outputs():
    before = _snapshot_data_raw()
    completed = subprocess.run(
        [sys.executable, "-m", "hydrolite", "healthcheck"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert Path("output/healthcheck/healthcheck_report.md").exists()
    assert Path("output/healthcheck/healthcheck_summary.xlsx").exists()
    assert _snapshot_data_raw() == before


def test_release_manifest_can_generate(tmp_path: Path):
    from hydrolite.release import build_release_manifest, release_directory_is_safe

    (tmp_path / "demo_project_package.zip").write_bytes(b"not-a-real-zip")
    manifest = build_release_manifest(tmp_path, test_summary="unit test")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["app_name"] == "HydroLite Studio"
    assert data["version"] == "0.6.0-dev"
    assert data["release_date"] == "2026-06-15"
    assert "demo_project_package.zip" in data["files"]
    assert release_directory_is_safe(tmp_path) is False


def test_release_directory_has_no_secrets_external_or_weights_if_present():
    from hydrolite.release import release_directory_is_safe

    release = Path("release")
    if release.exists():
        assert release_directory_is_safe(release) is True


def test_streamlit_sidebar_can_read_version():
    import hydrolite.ui.app as app

    assert app.__version__ == "0.6.0-dev"


def test_no_tracked_secrets_large_weights_or_external_repo():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    tracked = completed.stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)
