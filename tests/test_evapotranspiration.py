import pandas as pd
import pytest

from hydrolite.evapotranspiration import calculate_hargreaves_et, select_pet_method, validate_pet_inputs


def test_pet_user_gate_hargreaves_and_negative_rejection():
    frame=pd.DataFrame({"date":pd.date_range("2020-01-01",periods=3),"temperature_min_c":[10,11,12],"temperature_max_c":[20,21,22],"temperature_mean_c":[15,16,17]})
    assert select_pet_method(frame)=="Hargreaves_Samani"
    assert (calculate_hargreaves_et(frame,22.6)>=0).all()
    assert validate_pet_inputs(frame,"FAO56_Penman_Monteith")["status"]=="failed"
    from hydrolite.evapotranspiration import normalize_pet_units
    with pytest.raises(ValueError): normalize_pet_units([-1])
