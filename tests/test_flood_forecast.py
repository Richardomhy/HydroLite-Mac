from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def test_flood_forecast_demo_outputs_and_gates(tmp_path: Path):
    from hydrolite.flood_forecast import run_flood_forecast_demo, validate_flood_forecast_bundle, validate_flood_forecast_outputs

    output = tmp_path / "forecast"
    result = run_flood_forecast_demo(output)
    assert result["status"] == "passed_synthetic_demo"
    assert result["rainfall"]["member_id"].nunique() == 6
    assert (result["physics"]["member_summary"]["run_status"] == "success").sum() == 6
    assert set(result["physics"]["hms_summary"]["status"]) == {"skipped_optional_local"}
    assert validate_flood_forecast_outputs(output)["status"] == "passed"
    assert validate_flood_forecast_bundle(output)["status"] == "passed"
    with zipfile.ZipFile(output / "flood_forecast_bundle.zip") as archive:
        names = archive.namelist()
    assert not any(name.endswith((".dss", ".h5", ".hdf5", ".pt", ".pth", ".ckpt", ".onnx", ".joblib")) for name in names)


def test_flood_forecast_streamlit_page_imports():
    import hydrolite.ui.pages.flood_forecast as page

    assert callable(page.render)
