from __future__ import annotations

from pathlib import Path
import json
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


def test_qgis_bridge_imports_and_detects_without_crashing(tmp_path: Path):
    import hydrolite.qgis_bridge as qgis_bridge

    apps = qgis_bridge.detect_qgis_app_paths()
    processes = qgis_bridge.detect_qgis_process_candidates()
    diagnosis = qgis_bridge.build_qgis_diagnosis()
    outputs = qgis_bridge.write_qgis_diagnosis(tmp_path)
    recommendation = qgis_bridge.recommend_qgis_bridge_mode(diagnosis)

    assert isinstance(apps["qgis_apps"], list)
    assert processes
    assert diagnosis["status"] in {"available", "warning"}
    assert outputs["md"].exists()
    assert outputs["json"].exists()
    assert recommendation["mode"] in {"qgis_process", "PyQGIS", "QGIS plugin", "暂不可用"}
    assert json.loads(outputs["json"].read_text(encoding="utf-8"))["status"] in {"available", "warning"}


def test_qgis_cli_commands_execute():
    for command in (("qgis", "paths"), ("qgis", "recommend"), ("qgis", "diagnose")):
        completed = subprocess.run(
            [sys.executable, "-m", "hydrolite", *command],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
    assert Path("output/qgis/qgis_diagnosis.md").exists()
    assert Path("output/qgis/qgis_diagnosis.json").exists()


def test_qgis_streamlit_page_imports():
    import hydrolite.ui.app as app
    import hydrolite.ui.pages.qgis_bridge as qgis_bridge_page

    assert callable(qgis_bridge_page.render)
    assert "QGIS Bridge" in app.PAGES


def test_qgis_checks_do_not_modify_data_raw():
    before = _snapshot_data_raw()
    assert before
    subprocess.run([sys.executable, "-m", "hydrolite", "qgis", "paths"], check=False, capture_output=True, text=True)
    assert _snapshot_data_raw() == before


def test_qgis_no_tracked_secrets_external_or_model_weights():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    assert completed.returncode == 0, completed.stderr
    tracked = completed.stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)


def test_qgis_existing_tags_not_moved():
    expected = {
        "v0.5.0-alpha.2": ALPHA_TAG_COMMIT,
        "v0.6.0-beta": BETA_TAG_COMMIT,
        "v0.6.0-beta.1": BETA_1_TAG_COMMIT,
    }
    for tag, commit in expected.items():
        completed = subprocess.run(["git", "rev-parse", tag], capture_output=True, text=True, check=False, timeout=60)
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == commit
