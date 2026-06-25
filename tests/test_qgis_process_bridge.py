from __future__ import annotations

from pathlib import Path
import csv
import subprocess
import sys


ALPHA_TAG_COMMIT = "e81f194cbca58c3a88f8176b6da114d6a46ee1c6"
BETA_TAG_COMMIT = "67a386dd0de53ef7c22bdbd054adaf7c5aef122b"
BETA_1_TAG_COMMIT = "616fa6754b73b64d222ad508c1ab57bb52364365"
DEMO_LAYER = Path("data_demo/gis/demo_subbasins.geojson")


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(Path("data_raw").rglob("*"))
        if path.is_file()
    }


def test_qgis_process_bridge_functions_import():
    from hydrolite.qgis_bridge import (
        get_qgis_process_path,
        qgis_bridge_demo,
        qgis_export_attributes_csv,
        qgis_export_vector,
        qgis_layer_info,
        qgis_process_algorithms,
        qgis_process_plugins,
        qgis_process_version,
        qgis_validate_vector_layer,
        run_qgis_process,
    )

    assert callable(get_qgis_process_path)
    assert callable(run_qgis_process)
    assert callable(qgis_process_version)
    assert callable(qgis_process_plugins)
    assert callable(qgis_process_algorithms)
    assert callable(qgis_layer_info)
    assert callable(qgis_validate_vector_layer)
    assert callable(qgis_export_vector)
    assert callable(qgis_export_attributes_csv)
    assert callable(qgis_bridge_demo)


def test_demo_geojson_files_exist():
    for path in (
        Path("data_demo/gis/demo_basin_boundary.geojson"),
        Path("data_demo/gis/demo_reaches.geojson"),
        DEMO_LAYER,
    ):
        assert path.exists()


def test_layer_info_validate_and_csv_export(tmp_path: Path):
    from hydrolite.qgis_bridge import qgis_export_attributes_csv, qgis_layer_info, qgis_validate_vector_layer

    info = qgis_layer_info(DEMO_LAYER)
    validation = qgis_validate_vector_layer(DEMO_LAYER)
    csv_path = tmp_path / "attributes.csv"
    csv_result = qgis_export_attributes_csv(DEMO_LAYER, csv_path)

    assert info["exists"] is True
    assert info["qgis_recognized"] is True
    assert info["feature_count"] == 2
    assert "subbasin_id" in info["fields"]
    assert validation["status"] == "passed"
    assert csv_result["status"] == "success"
    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and "subbasin_id" in rows[0]


def test_export_vector_and_demo_outputs(tmp_path: Path):
    from hydrolite.qgis_bridge import qgis_bridge_demo, qgis_export_vector

    exported = tmp_path / "demo_subbasins_export.geojson"
    result = qgis_export_vector(DEMO_LAYER, exported)
    summary = qgis_bridge_demo(tmp_path / "demo")

    assert result["status"] == "success"
    assert exported.exists()
    assert Path(summary["outputs"]["report"]).exists()
    assert Path(summary["outputs"]["summary"]).exists()
    assert Path(summary["outputs"]["export_geojson"]).exists()
    assert Path(summary["outputs"]["export_csv"]).exists()


def test_qgis_process_bridge_cli_executes():
    commands = [
        ("qgis", "version"),
        ("qgis", "layer-info", str(DEMO_LAYER)),
        ("qgis", "validate-layer", str(DEMO_LAYER)),
        ("qgis", "export-csv", str(DEMO_LAYER), "output/qgis_bridge_demo/test_cli_attributes.csv"),
        ("qgis", "demo"),
    ]
    for command in commands:
        completed = subprocess.run(
            [sys.executable, "-m", "hydrolite", *command],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert completed.returncode == 0, completed.stderr


def test_qgis_process_bridge_streamlit_page_imports():
    import hydrolite.ui.app as app
    import hydrolite.ui.pages.qgis_bridge as qgis_bridge_page

    assert callable(qgis_bridge_page.render)
    assert "QGIS Bridge" in app.PAGES


def test_qgis_process_bridge_does_not_modify_data_raw():
    before = _snapshot_data_raw()
    assert before
    subprocess.run([sys.executable, "-m", "hydrolite", "qgis", "version"], check=False, capture_output=True, text=True)
    assert _snapshot_data_raw() == before


def test_qgis_process_bridge_no_tracked_secrets_external_or_weights():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    assert completed.returncode == 0, completed.stderr
    tracked = completed.stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)


def test_qgis_process_bridge_existing_tags_not_moved():
    expected = {
        "v0.5.0-alpha.2": ALPHA_TAG_COMMIT,
        "v0.6.0-beta": BETA_TAG_COMMIT,
        "v0.6.0-beta.1": BETA_1_TAG_COMMIT,
    }
    for tag, commit in expected.items():
        completed = subprocess.run(["git", "rev-parse", tag], capture_output=True, text=True, check=False, timeout=60)
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == commit
