from pathlib import Path


def test_geojson_crs_extent_geometry_and_source_unchanged():
    from hydrolite.spatial_ingestion import inspect_crs, inspect_extent, validate_geometry
    from hydrolite.workspace import calculate_file_checksum

    path = Path("templates/data_upload/watershed_boundary.geojson")
    before = calculate_file_checksum(path)
    assert inspect_crs(path)["crs"] == "EPSG:4326"
    assert inspect_extent(path)["status"] == "passed"
    assert validate_geometry(path)["status"] == "passed"
    assert calculate_file_checksum(path) == before
