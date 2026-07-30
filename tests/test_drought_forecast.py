from pathlib import Path
import subprocess
import sys

from hydrolite.drought_forecast import validate_drought_forecast_config
from hydrolite.ui.pages.drought_center import read_drought_outputs
from hydrolite.workflow_engine import list_workflow_stages


ROOT=Path(__file__).resolve().parents[1]


def test_drought_forecast_contract_cli_ui_and_stages():
    assert validate_drought_forecast_config({"mode":"scenario_simulation","lead_months":[1,3,6,12],"maximum_members":10})["status"]=="passed"
    completed=subprocess.run([sys.executable,"-m","hydrolite","drought","readiness","data_demo/drought"],cwd=ROOT,text=True,capture_output=True)
    assert completed.returncode==0,completed.stdout+completed.stderr
    assert isinstance(read_drought_outputs(),dict)
    ids={row["stage_id"]:row["status"] for row in list_workflow_stages()}
    expected={"continuous_hydrology","evapotranspiration","soil_water_balance","groundwater_baseflow","drought_indices","drought_event_catalog","drought_monitoring","drought_scenarios","drought_forecast","drought_data_assimilation","drought_model_validation"}
    assert expected<=set(ids) and all(ids[name]=="partial" for name in expected)
