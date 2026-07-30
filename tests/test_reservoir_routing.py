from pathlib import Path
import pandas as pd
import pytest
from hydrolite.reservoir_routing import load_stage_area_volume_curve, load_stage_discharge_curve, route_reservoir_level_pool, run_reservoir_demo, validate_stage_area_volume_curve

ROOT=Path(__file__).resolve().parents[1]
def test_reservoir_demo_and_balance(tmp_path):
    result=run_reservoir_demo(ROOT/'data_demo/reservoir/demo_reservoir_config.yaml',tmp_path)
    assert result['metrics']['peak_outflow_cms'] < result['metrics']['peak_inflow_cms']
    assert abs(result['metrics']['residual_m3']) < 1e-6
def test_negative_area_and_missing_discharge_rejected():
    curve=pd.DataFrame({'stage_m':[1,2],'area_m2':[1,-1],'storage_m3':[1,2]})
    assert validate_stage_area_volume_curve(curve)['status']=='failed'
    with pytest.raises(ValueError,match='discharge_curve_missing'):
        route_reservoir_level_pool(pd.DataFrame({'inflow_cms':[0]}),pd.DataFrame({'stage_m':[1,2],'area_m2':[1,1],'storage_m3':[0,10]}),None,{})
