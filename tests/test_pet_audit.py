import pandas as pd
from hydrolite.pet_audit import calculate_reference_hargreaves_independent

def test_independent_pet_is_positive():
    data=pd.DataFrame({"date":["2020-02-29"],"temperature_min_c":[10],"temperature_max_c":[20],"temperature_mean_c":[15]})
    assert calculate_reference_hargreaves_independent(data,22.6).iloc[0]>0
