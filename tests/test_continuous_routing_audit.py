import pandas as pd
from hydrolite.continuous_routing_audit import calculate_routing_mass_balance

def test_routing_balance():
    data=pd.DataFrame({"inflow_m3":[1.],"outflow_m3":[.5],"final_storage_m3":[.5],"residual_m3":[0.]})
    assert calculate_routing_mass_balance(data)["status"]=="passed"
