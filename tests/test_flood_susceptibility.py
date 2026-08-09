import json
import zipfile

from hydrolite.flood_susceptibility import train_adaptive, train_baselines


def test_supervised_baselines_and_optional_rl(tmp_path):
    assert train_baselines("demo",tmp_path)["status"]=="passed"
    result=train_adaptive("demo",tmp_path)
    assert result["status"]=="passed"
    assert result["rl_executed"] is False
    manifest = json.loads((tmp_path / "reports/flood_susceptibility_manifest.json").read_text())
    assert manifest["spatial_blocks"] >= 20 and manifest["factor_count"] >= 12
    assert manifest["validation_level"] == "synthetic_spatial_demo"
    expected = [
        "data_quality/inventory_qc.xlsx", "data_quality/factor_qc.xlsx",
        "spatial_validation/block_metrics.xlsx", "models/model_metrics.xlsx",
        "models/confusion_matrix.xlsx", "mapping/susceptibility_map.geojson",
        "xai/global_importance.xlsx", "xai/local_explanations.xlsx",
    ]
    assert all((tmp_path / name).exists() for name in expected)
    with zipfile.ZipFile(tmp_path / "reports/flood_susceptibility_bundle.zip") as archive:
        names = archive.namelist()
        assert not any("data_raw" in name or "external" in name for name in names)
