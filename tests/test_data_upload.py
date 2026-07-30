from pathlib import Path
import zipfile

import pandas as pd


def test_upload_csv_xlsx_geojson_ascii_and_unsupported(tmp_path: Path):
    from hydrolite.data_upload import detect_file_format, detect_table_structure, inspect_uploaded_file

    csv_path = Path("templates/data_upload/rainfall_observed.csv")
    assert inspect_uploaded_file(csv_path)["classification"]["dataset_type"] == "rainfall_observed"
    xlsx = tmp_path / "book.xlsx"
    with pd.ExcelWriter(xlsx) as writer:
        pd.DataFrame({"时间": ["2026-01-01"], "降雨量": [1]}).to_excel(writer, sheet_name="rain", index=False)
        pd.DataFrame({"note": ["select sheet"]}).to_excel(writer, sheet_name="notes", index=False)
    assert detect_table_structure(xlsx)["status"] == "needs_sheet_selection"
    assert inspect_uploaded_file("templates/data_upload/watershed_boundary.geojson")["format"] == "geojson"
    assert inspect_uploaded_file("data_demo/workspaces/demo_real_project/demo_dem.asc")["raster"]["status"] == "passed"
    unknown = tmp_path / "file.xyz"
    unknown.write_text("x")
    assert detect_file_format(unknown) == "unsupported"


def test_zip_shapefile_parts_and_path_traversal(tmp_path: Path):
    from hydrolite.data_upload import detect_file_format, reject_unsafe_archive

    shape = tmp_path / "shape.zip"
    with zipfile.ZipFile(shape, "w") as archive:
        for suffix in (".shp", ".shx", ".dbf", ".prj"):
            archive.writestr(f"basin{suffix}", "demo")
    assert detect_file_format(shape) == "zip_shapefile"
    assert reject_unsafe_archive(shape)["status"] == "passed"
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.csv", "bad")
    assert reject_unsafe_archive(unsafe)["status"] == "failed"
