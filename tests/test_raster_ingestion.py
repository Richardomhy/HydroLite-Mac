def test_ascii_raster_and_geographic_dem_warning():
    from hydrolite.raster_ingestion import inspect_raster, validate_raster

    path = "data_demo/workspaces/demo_real_project/demo_dem.asc"
    assert inspect_raster(path)["status"] == "passed"
    assert validate_raster(path, "dem")["quality_status"] == "ready_with_warnings"


def test_optional_geotiff_netcdf_hdf5_degrade(tmp_path):
    from hydrolite.raster_ingestion import inspect_raster

    for suffix in (".tif", ".nc", ".h5"):
        path = tmp_path / f"empty{suffix}"
        path.write_bytes(b"not a real raster")
        assert inspect_raster(path)["status"] in {"optional_backend_required", "invalid"}
