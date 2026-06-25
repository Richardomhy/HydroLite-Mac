from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ALPHA_TAG_COMMIT = "e81f194cbca58c3a88f8176b6da114d6a46ee1c6"
BETA_TAG_COMMIT = "67a386dd0de53ef7c22bdbd054adaf7c5aef122b"
BETA_1_TAG_COMMIT = "616fa6754b73b64d222ad508c1ab57bb52364365"
SUBBASINS = Path("data_demo/gis/demo_subbasins.geojson")
REACHES = Path("data_demo/gis/demo_reaches.geojson")
BASIN = Path("data_demo/gis/demo_basin_boundary.geojson")


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(Path("data_raw").rglob("*"))
        if path.is_file()
    }


def test_qgis_to_hydrolite_functions(tmp_path: Path):
    from hydrolite.qgis_bridge import (
        convert_geojson_to_reaches_csv,
        convert_geojson_to_subbasins_csv,
        convert_qgis_layers_to_hydrolite_inputs,
        export_basin_boundary_geojson,
        infer_hydrolite_field_mapping,
        validate_qgis_to_hydrolite_outputs,
    )

    assert infer_hydrolite_field_mapping(SUBBASINS, "subbasins")["mapping"]["subbasin_id"] == "subbasin_id"
    assert infer_hydrolite_field_mapping(REACHES, "reaches")["mapping"]["reach_id"] == "reach_id"
    assert convert_geojson_to_subbasins_csv(SUBBASINS, tmp_path / "subbasins.csv")["status"] == "success"
    assert convert_geojson_to_reaches_csv(REACHES, tmp_path / "reaches.csv")["status"] == "success"
    assert export_basin_boundary_geojson(BASIN, tmp_path / "basin_boundary.geojson")["status"] == "success"
    result = convert_qgis_layers_to_hydrolite_inputs(SUBBASINS, REACHES, BASIN, tmp_path / "dataset")
    validation = validate_qgis_to_hydrolite_outputs(tmp_path / "dataset")
    assert result["status"] == "success"
    for name in (
        "subbasins.csv",
        "reaches.csv",
        "basin_boundary.geojson",
        "qgis_to_hydrolite_mapping_report.md",
        "qgis_to_hydrolite_summary.xlsx",
        "qgis_to_hydrolite_manifest.json",
    ):
        assert (tmp_path / "dataset" / name).exists()
    assert validation["status"] in {"passed", "warning"}


def test_qgis_to_hydrolite_cli_executes():
    commands = [
        ("qgis", "infer-mapping", str(SUBBASINS), "subbasins"),
        ("qgis", "infer-mapping", str(REACHES), "reaches"),
        ("qgis", "convert-subbasins", str(SUBBASINS), "output/qgis_to_hydrolite_test/subbasins.csv"),
        ("qgis", "convert-reaches", str(REACHES), "output/qgis_to_hydrolite_test/reaches.csv"),
        ("qgis", "export-basin", str(BASIN), "output/qgis_to_hydrolite_test/basin_boundary.geojson"),
        ("qgis", "to-hydrolite", str(SUBBASINS), str(REACHES), str(BASIN), "output/qgis_to_hydrolite_test"),
        ("qgis", "validate-hydrolite", "output/qgis_to_hydrolite_test"),
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


def test_qgis_to_hydrolite_streamlit_imports():
    import hydrolite.ui.pages.qgis_bridge as qgis_bridge_page

    assert callable(qgis_bridge_page.render)


def test_qgis_to_hydrolite_does_not_modify_data_raw():
    before = _snapshot_data_raw()
    assert before
    subprocess.run([sys.executable, "-m", "hydrolite", "qgis", "infer-mapping", str(SUBBASINS), "subbasins"], check=False)
    assert _snapshot_data_raw() == before


def test_qgis_to_hydrolite_no_secrets_or_weights_and_tags_unchanged():
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60).stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/openhydronet/flood-forecasting") for path in tracked)
    for tag, commit in {
        "v0.5.0-alpha.2": ALPHA_TAG_COMMIT,
        "v0.6.0-beta": BETA_TAG_COMMIT,
        "v0.6.0-beta.1": BETA_1_TAG_COMMIT,
    }.items():
        completed = subprocess.run(["git", "rev-parse", tag], capture_output=True, text=True, check=False, timeout=60)
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == commit
