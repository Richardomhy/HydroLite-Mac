"""Water/soil conservation scenario wrapper; never overwrites source cases."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import pandas as pd
import yaml
from hydrolite.calibration import _project_case
from hydrolite.config import load_case
from hydrolite.project import run_project_case

def _path(v:str|Path)->Path:return Path(v).expanduser().resolve()
def load_conservation_scenario(config_path:str|Path)->dict[str,Any]:
    data=yaml.safe_load(_path(config_path).read_text()) or {}
    return validate_conservation_scenario(data)
def validate_conservation_scenario(config:dict[str,Any])->dict[str,Any]:
    changes=config.get("hydrolite_changes") or {}
    if not -30<=float(changes.get("cn_delta",-8))<=0: raise ValueError("Conservation CN delta must be within -30..0.")
    if not 0<=float(changes.get("initial_abstraction_ratio",.25))<=.5: raise ValueError("Initial abstraction ratio must be 0..0.5.")
    if float(changes.get("lag_multiplier",1.2))<=0: raise ValueError("lag_multiplier must be positive.")
    return config
def map_conservation_measures_to_subbasins(project_dir:str|Path,scenario:dict[str,Any])->pd.DataFrame:
    config=load_case(_project_case(_path(project_dir)));df=pd.read_csv(config.subcatchments_csv);df["measure"]=";".join((scenario.get("measures") or ["custom"]));return df[["subbasin_id","measure"]]
def build_hydrolite_conservation_parameters(project_dir:str|Path,scenario:dict[str,Any],output_dir:str|Path)->dict[str,Path]:
    project=_path(project_dir);base=load_case(_project_case(project));changes=scenario.get("hydrolite_changes") or {};generated=project/"data/generated/conservation";generated.mkdir(parents=True,exist_ok=True)
    sub=pd.read_csv(base.subcatchments_csv);sub["cn"]=(pd.to_numeric(sub["cn"])+float(changes.get("cn_delta",-8))).clip(30,98);sub["initial_abstraction_ratio"]=float(changes.get("initial_abstraction_ratio",.25));sub["lag_time_hr"]=pd.to_numeric(sub["lag_time_hr"])*float(changes.get("lag_multiplier",1.2));sub_path=generated/"subbasins_conservation.csv";sub.to_csv(sub_path,index=False)
    raw=yaml.safe_load(_project_case(project).read_text());raw["name"]="qgis_demo_conservation";raw["inputs"]["subcatchments"]=str(sub_path);raw["outputs"]["directory"]="output/qgis_demo_conservation";case=project/"cases/qgis_demo_conservation.yaml";case.write_text(yaml.safe_dump(raw,sort_keys=False));manifest=generated/"conservation_manifest.json";manifest.write_text(json.dumps({"scenario":scenario,"synthetic_or_single_event":True},indent=2));return {"case":case,"subbasins":sub_path,"manifest":manifest}
def calculate_water_retention_amount(baseline_runoff:float,scenario_runoff:float)->float:return float(baseline_runoff-scenario_runoff)
def calculate_soil_conservation_summary(rusle_baseline:float,rusle_scenario:float)->dict[str,float]: return {"soil_conservation_t_yr":float(rusle_baseline-rusle_scenario),"soil_conservation_percent":float((rusle_baseline-rusle_scenario)/rusle_baseline*100) if rusle_baseline else float("nan")}
def run_hydrolite_conservation_scenario(project_dir:str|Path,scenario:dict[str,Any],output_dir:str|Path)->dict[str,Any]:
    project=_path(project_dir);paths=build_hydrolite_conservation_parameters(project,scenario,output_dir);baseline=run_project_case(project,"qgis_demo.yaml");run=run_project_case(project,paths["case"].name)
    def volume(p:Path)->float:
        frame=pd.read_csv(p);return float(frame["outflow_cms"].sum()*3600)
    b,s=volume(baseline.result_flow_csv),volume(run.result_flow_csv);root=_path(output_dir);root.mkdir(parents=True,exist_ok=True)
    summary=pd.DataFrame([{"baseline_runoff_volume_m3":b,"conservation_runoff_volume_m3":s,"water_retention_amount_m3_event":calculate_water_retention_amount(b,s),"runoff_reduction_percent":(b-s)/b*100 if b else None,"warnings":"single-event amount; do not annualize"}])
    with pd.ExcelWriter(root/"conservation_summary.xlsx") as w:summary.to_excel(w,index=False)
    return {"case":paths["case"],"summary":summary,"output_dir":root}
def write_conservation_report(output_dir:str|Path,result:dict[str,Any])->Path:
    p=_path(output_dir)/"conservation_report.md";p.write_text("# Conservation scenario\n\nWater retention is baseline event runoff minus conservation event runoff; it is not derived from RUSLE and is not annualized.\n");return p
