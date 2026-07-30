import pandas as pd

from hydrolite.drought_assimilation import run_drought_state_assimilation, validate_drought_assimilation


def test_drought_assimilation_logs_adjustment_and_nonnegative():
    state={"subbasins":{"A":{"upper_soil_storage_mm":50,"lower_soil_storage_mm":100,"groundwater_storage_mm":80,"reservoir_storage_m3":1000}}}
    observations=pd.DataFrame([{"date":"2020-01-01","subbasin_id":"A","variable":"soil_moisture_mm","value":180}])
    result=run_drought_state_assimilation(state,observations,{"soil_moisture_gain":0.2})
    assert "assimilation_adjustment_mm" in result["adjustments"]
    assert validate_drought_assimilation(result)["status"]=="passed"
