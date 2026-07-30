import pandas as pd

from hydrolite.continuous_hydrology import DEFAULT_PARAMETERS, initialize_continuous_state, run_continuous_period, validate_continuous_water_balance


def test_continuous_state_and_daily_balance():
    config={"model":{"synthetic_demo":True},"pet":{"method":"user_supplied_pet"},"parameters":DEFAULT_PARAMETERS,"routing":{"method":"linear_reservoir","k_days":2},"subbasins":[{"subbasin_id":"A","area_km2":2},{"subbasin_id":"B","area_km2":3}]}
    forcing=pd.DataFrame([{"date":date,"subbasin_id":subbasin,"precipitation_mm":10 if day%3==0 else 0,"potential_et_mm":3,"temperature_mean_c":20} for day,date in enumerate(pd.date_range("2020-01-01",periods=20)) for subbasin in ("A","B")])
    result=run_continuous_period(forcing,DEFAULT_PARAMETERS,initialize_continuous_state(config),config)
    assert validate_continuous_water_balance(result)["status"]=="passed"
    assert len(result["states"])==40
    assert result["routing"].iloc[-1]["final_storage_m3"]>=0
    assert (result["states"].filter(regex="storage").select_dtypes("number")>=0).all().all()
