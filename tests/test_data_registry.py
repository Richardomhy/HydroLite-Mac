def test_data_registry_has_required_types_and_reports(tmp_path):
    from hydrolite.data_registry import get_dataset_type, list_dataset_types, write_data_registry_report

    rows = list_dataset_types()
    assert len(rows) >= 70
    for name in ("rainfall_observed", "dem", "water_quality_observations", "ICESat2_ATL13", "swmm_inp"):
        assert get_dataset_type(name)["dataset_type_id"] == name
    for name in ("daily_meteorology", "potential_evapotranspiration", "soil_moisture_observed", "groundwater_storage", "reservoir_daily_balance", "vegetation_index_timeseries", "climate_forecast_ensemble", "drought_event_catalog"):
        assert get_dataset_type(name)["dataset_type_id"] == name
    outputs = write_data_registry_report(tmp_path)
    assert outputs["registry"].exists()
    assert outputs["formats"].exists()
