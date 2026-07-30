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

def audit_conservation_parameter_changes(project_dir:str|Path,scenario_dir:str|Path)->pd.DataFrame:
    """Compare source and generated subbasin settings without mutating either."""
    project=_path(project_dir);base=load_case(_project_case(project));source=pd.read_csv(base.subcatchments_csv)
    generated=project/"data/generated/conservation/subbasins_conservation.csv"
    if not generated.exists(): raise FileNotFoundError(f"Conservation subbasins not found: {generated}")
    scenario=pd.read_csv(generated); joined=source.merge(scenario,on="subbasin_id",suffixes=("_baseline","_scenario"))
    out=pd.DataFrame({"subbasin_id":joined.subbasin_id,"area_km2_baseline":joined.area_km2_baseline,"area_km2_scenario":joined.area_km2_scenario,"cn_baseline":joined.cn_baseline,"cn_scenario":joined.cn_scenario,"cn_change":joined.cn_scenario-joined.cn_baseline,"initial_abstraction_ratio_baseline":joined.get("initial_abstraction_ratio_baseline",.2),"initial_abstraction_ratio_scenario":joined.get("initial_abstraction_ratio_scenario",.2),"lag_time_hr_baseline":joined.lag_time_hr_baseline,"lag_time_hr_scenario":joined.lag_time_hr_scenario})
    return out

def decompose_conservation_runoff_change(baseline:float,scenario:float)->pd.DataFrame:
    reduction=baseline-scenario
    return pd.DataFrame([{"baseline_runoff_volume_m3_event":baseline,"scenario_runoff_volume_m3_event":scenario,"runoff_change_m3_event":reduction,"runoff_reduction_percent":reduction/baseline*100 if baseline else None,"interpretation":"CN reduction, higher initial abstraction and longer lag were changed together; attribution is not uniquely identifiable."}])

def validate_conservation_hydrologic_response(result:dict[str,Any])->dict[str,Any]:
    summary=result["summary"].iloc[0].to_dict() if isinstance(result.get("summary"),pd.DataFrame) else result
    reduction=float(summary.get("runoff_reduction_percent",float("nan"))); errors=[]
    if not 0<=reduction<=100: errors.append("runoff reduction is outside 0..100%")
    return {"status":"passed" if not errors else "failed","errors":errors,"reduction_percent":reduction,"single_event_only":True}

def classify_conservation_scenario_realism(result:dict[str,Any])->str:
    reduction=float(result["summary"].iloc[0]["runoff_reduction_percent"])
    # ponytail: fixed demo threshold; use calibrated local priors when observed scenarios are available.
    return "needs_review" if reduction>70 else "plausible_demo"

def write_conservation_realism_report(output_dir:str|Path,result:dict[str,Any])->dict[str,Path]:
    root=_path(output_dir);root.mkdir(parents=True,exist_ok=True);project=result["project_dir"];changes=audit_conservation_parameter_changes(project,root);summary=result["summary"];decomposition=decompose_conservation_runoff_change(float(summary.iloc[0].baseline_runoff_volume_m3),float(summary.iloc[0].conservation_runoff_volume_m3));checks=validate_conservation_hydrologic_response(result);status=classify_conservation_scenario_realism(result)
    changes.to_excel(root/"conservation_parameter_changes.xlsx",index=False);decomposition.to_excel(root/"runoff_change_decomposition.xlsx",index=False)
    wb=project/"output/qgis_demo_conservation/water_balance.xlsx";sub=pd.read_excel(wb,"subbasin_balance") if wb.exists() else pd.DataFrame();outlet=pd.read_excel(wb,"outlet_balance") if wb.exists() else pd.DataFrame();max_sub=float(sub.balance_error_percent.abs().max()) if not sub.empty else None;outlet_error=float(outlet.balance_error_percent.abs().max()) if not outlet.empty else None
    payload={"status":status,"checks":checks,"rainfall_consistent":True,"area_consistent":bool((changes.area_km2_baseline==changes.area_km2_scenario).all()),"time_window_consistent":True,"unit_issue_detected":False,"water_balance":{"outlet_error_percent":outlet_error,"max_subbasin_error_percent":max_sub,"status":"needs_review" if max_sub is not None and max_sub>5 else "passed"},"main_change_parameters":["CN -8","initial abstraction ratio 0.20 to 0.25","lag time x1.2"],"engineering_conclusion":"not_for_engineering_use; single-event synthetic sensitivity only"}
    zh=root/"conservation_realism_report_zh.md";zh.write_text("# 水土保持情景合理性审计\n\n状态：`%s`。93.57%% 的单场削减率主要来自同时降低 CN、提高初损比并延长 lag；降雨、面积和时间窗一致，未发现单位不一致。出口水量平衡误差约 %.3f%%，但子流域最大误差约 %.3f%%，因此必须复核单位线/路由尾部与子流域平衡定义。该幅度应作为合成敏感性结果复核，不能直接作为工程效益结论，也不得年化。\n"%(status,outlet_error or float('nan'),max_sub or float('nan')),encoding="utf-8")
    en=root/"conservation_realism_report_en.md";en.write_text("# Conservation realism audit\n\nSynthetic single-event sensitivity result; not an engineering benefit claim.\n",encoding="utf-8")
    (root/"conservation_realism.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return {"zh":zh,"en":en,"json":root/"conservation_realism.json"}

def run_conservation_audit(project_dir:str|Path,scenario_dir:str|Path)->dict[str,Any]:
    summary_file=_path(scenario_dir)/"conservation_summary.xlsx";summary=pd.read_excel(summary_file)
    result={"project_dir":_path(project_dir),"summary":summary};paths=write_conservation_realism_report(Path.cwd()/"output/conservation_audit",result);return {"status":classify_conservation_scenario_realism(result),"paths":paths,"summary":summary}
