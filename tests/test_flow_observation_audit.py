import pandas as pd
from hydrolite.flow_observation_audit import convert_observed_flow_to_volume

def test_cms_is_integrated_daily():
    value=convert_observed_flow_to_volume(pd.DataFrame({"date":["2020-01-01"],"streamflow_cms":[1.]}),1.)
    assert value.observed_volume_m3_d.iloc[0]==86400
