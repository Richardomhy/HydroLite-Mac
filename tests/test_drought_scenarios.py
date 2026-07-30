import pandas as pd

from hydrolite.drought_scenarios import create_precipitation_scale_scenarios, validate_drought_scenarios
from hydrolite.drought_workflow import create_drought_demo_scenarios


def test_user_scenario_is_not_forecast():
    frame=pd.DataFrame({"date":["2020-01-01"],"subbasin_id":["A"],"precipitation_mm":[10]})
    result=create_precipitation_scale_scenarios(frame,[0.8,0.6])
    assert set(result["scenario_type"])=={"user_scenario"}
    assert validate_drought_scenarios(result)["status"]=="passed"


def test_demo_has_all_eight_bounded_members(tmp_path):
    result=create_drought_demo_scenarios(output_dir=tmp_path)
    assert result["member_id"].nunique()==8
    assert "pet_1.15" in set(result["member_id"])
