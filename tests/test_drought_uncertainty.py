import pandas as pd

from hydrolite.drought_uncertainty import calculate_drought_class_fraction, calculate_index_quantiles


def test_drought_uncertainty_quantiles_and_scenario_fraction():
    frame=pd.DataFrame({"lead_month":[1,1,3,3],"member_id":["a","b","a","b"],"composite_index":[-1,0,-2,1],"drought_class":["moderate","normal","extreme","normal"]})
    assert {"p05","p25","p50","p75","p95"}<=set(calculate_index_quantiles(frame))
    assert "scenario_member_fraction" in calculate_drought_class_fraction(frame)
