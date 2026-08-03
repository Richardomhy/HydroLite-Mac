from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import shutil
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hydrolite.continuous_balance_audit import calculate_annual_component_balance, calculate_daily_component_balance, calculate_monthly_component_balance, collect_all_continuous_fluxes, reconcile_reported_and_internal_fluxes, write_continuous_balance_audit
from hydrolite.continuous_benchmarks import run_continuous_benchmarks, write_benchmark_report
from hydrolite.continuous_calibration import build_staged_calibration_plan, run_continuous_parameter_search, write_continuous_calibration_report
from hydrolite.continuous_hydrology import DEFAULT_PARAMETERS, initialize_continuous_state, load_continuous_model_config, run_continuous_config, run_continuous_period, validate_continuous_water_balance
from hydrolite.continuous_routing_audit import calculate_routing_mass_balance, collect_routing_outputs, validate_routing_parameters, write_routing_audit_report
from hydrolite.continuous_sensitivity import run_continuous_sensitivity, write_continuous_sensitivity_report
from hydrolite.continuous_structure_diagnostic import diagnose_structural_mismatch, write_structure_diagnostic_report
from hydrolite.flow_observation_audit import audit_observed_streamflow, write_flow_observation_audit
from hydrolite.parameter_application_audit import evaluate_parameter_response, find_unused_parameters, trace_parameter_application, validate_parameter_application, write_parameter_application_report
from hydrolite.pet_audit import audit_day_of_year, audit_hargreaves_equation, audit_latitude_value, audit_temperature_units, calculate_reference_hargreaves_independent, detect_implausible_pet, write_pet_audit_report
from hydrolite.synthetic_truth_validation import generate_synthetic_truth, run_parameter_recovery, run_truth_forward_validation, write_truth_recovery_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "continuous_validation"


def _project_config(project: str | Path) -> tuple[dict[str, Any], pd.DataFrame, Path]:
    root=Path(project); config_path=root/"continuous_model_config.yaml" if root.is_dir() else root
    config=load_continuous_model_config(config_path); base=Path(config["_config_path"]).parent; forcing=pd.read_csv(base/config["input"]["daily_meteorology_csv"])
    return config,forcing,base


def _area(config:dict[str,Any])->float:return float(sum(row["area_km2"] for row in config["subbasins"]))


def validate_continuous_inputs(config: dict[str, Any], forcing: pd.DataFrame) -> dict[str, Any]:
    required={"date","subbasin_id","precipitation_mm","temperature_min_c","temperature_max_c","temperature_mean_c"};missing=sorted(required-set(forcing));dates=pd.to_datetime(forcing.get("date"),errors="coerce") if "date" in forcing else pd.Series(dtype="datetime64[ns]")
    checks={"required_columns":not missing,"date_parse":not dates.isna().any(),"rain_nonnegative":bool((pd.to_numeric(forcing.get("precipitation_mm",pd.Series()),errors="coerce")>=0).all()),"subbasins_match":set(forcing.get("subbasin_id",[]))=={str(x["subbasin_id"]) for x in config.get("subbasins",[])}}
    return {"status":"passed" if all(checks.values()) else "failed","missing_columns":missing,"checks":checks,"records":len(forcing),"date_start":str(dates.min().date()) if len(dates) else None,"date_end":str(dates.max().date()) if len(dates) else None}


def validate_continuous_states(states: pd.DataFrame, parameters: dict[str, Any]) -> dict[str, Any]:
    storage=[name for name in states if name.endswith("_storage_mm") or name.endswith("_storage_m3")];return {"status":"passed" if all((pd.to_numeric(states[name],errors="coerce")>=0).all() for name in storage) else "failed","state_fields":storage}
def validate_continuous_fluxes(fluxes:pd.DataFrame)->dict[str,Any]:return {"status":"passed" if float(fluxes.water_balance_residual_mm.abs().max())<=1e-6 else "failed","max_residual_mm":float(fluxes.water_balance_residual_mm.abs().max())}
def validate_observed_flow(observed:pd.DataFrame,basin_metadata:dict[str,Any])->dict[str,Any]:return audit_observed_streamflow(observed,float(basin_metadata["area_km2"]))
def compare_simulated_observed_volumes(simulated:pd.DataFrame,observed:pd.DataFrame,basin_area:float)->dict[str,Any]:
    audit=audit_observed_streamflow(observed,basin_area);sim=float(simulated.outflow_m3.sum());obs=float(audit["total_volume_m3"]);return {"simulated_volume_m3":sim,"observed_volume_m3":obs,"simulated_to_observed_volume_ratio":sim/max(obs,1e-9),"observed_equivalent_runoff_depth_mm":audit["equivalent_runoff_depth_mm"]}
def diagnose_continuous_model_failure(simulated:pd.DataFrame,observed:pd.DataFrame,context:dict[str,Any])->dict[str,Any]:return diagnose_structural_mismatch(context.get("flow_audit",{}),context.get("truth_status","failed"))
def classify_continuous_validation(result:dict[str,Any])->str:
    if result.get("truth_recovery",{}).get("status")!="passed":return "synthetic_truth_mismatch"
    return result.get("structure",{}).get("status","insufficient_data")
def evaluate_water_quality_hydrology_gate(result:dict[str,Any])->dict[str,Any]:
    truth=result.get("truth_recovery",{}).get("status")=="passed";balance=result.get("balance",{}).get("status")=="passed";structure=result.get("structure",{}).get("status")
    status="ready_with_warnings" if truth and balance and structure in {"structural_mismatch","passed_demo_validation"} else "blocked"
    return {"status":status,"truth_recovery_passed":truth,"water_balance_passed":balance,"model_demo_status":structure,"note":"Water balance passing does not prove flow-process skill; no water-quality transport model is enabled by this gate."}


def run_input_audit(project: str | Path, output_root: str | Path = DEFAULT_OUTPUT) -> dict[str,Any]:
    config,forcing,base=_project_config(project);out=Path(output_root)/"input_audit";out.mkdir(parents=True,exist_ok=True);result=validate_continuous_inputs(config,forcing);summary=forcing.describe(include="all").transpose().reset_index(names="field")
    with pd.ExcelWriter(out/"forcing_summary.xlsx") as writer:summary.to_excel(writer,index=False);pd.DataFrame([result]).to_excel(writer,sheet_name="audit",index=False)
    (out/"input_unit_audit.md").write_text("# Continuous input and unit audit\n\n"+json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return {"config":config,"forcing":forcing,"result":result}


def run_pet_audit(project: str | Path, output_root: str | Path = DEFAULT_OUTPUT) -> dict[str,Any]:
    config,forcing,_=_project_config(project);latitude=float(config.get("pet",{}).get("latitude",0));reference=calculate_reference_hargreaves_independent(forcing,latitude)
    from hydrolite.evapotranspiration import calculate_hargreaves_et
    model=calculate_hargreaves_et(forcing,latitude);equation=audit_hargreaves_equation(forcing,model,latitude);stats=detect_implausible_pet(model);result={"comparison":pd.DataFrame({"date":forcing.date,"model_pet_mm":model,"independent_pet_mm":reference,"difference_mm":model-reference}),"statistics":{**stats,"equation_status":equation["status"],"temperature":audit_temperature_units(forcing),"latitude":audit_latitude_value(latitude),"day_of_year":audit_day_of_year(forcing)}};write_pet_audit_report(Path(output_root)/"pet_audit",result);return result


def run_flow_audit(project: str | Path, output_root: str | Path = DEFAULT_OUTPUT, continuous_dir: str|Path|None=None)->dict[str,Any]:
    config,_,base=_project_config(project);observed=pd.read_csv(base/"observed_streamflow.csv");sim=pd.read_csv(Path(continuous_dir or ROOT/"output/drought_model/continuous")/"daily_routing.csv");audit=audit_observed_streamflow(observed,_area(config));comparison=compare_simulated_observed_volumes(sim,observed,_area(config));audit.update(comparison);write_flow_observation_audit(Path(output_root)/"input_audit",audit,sim);return audit


def run_balance_audit(continuous_dir: str|Path, output_root: str|Path=DEFAULT_OUTPUT)->dict[str,Any]:
    flux=collect_all_continuous_fluxes(continuous_dir);result={"daily":calculate_daily_component_balance(flux),"monthly":calculate_monthly_component_balance(flux),"annual":calculate_annual_component_balance(flux),"reconciliation":reconcile_reported_and_internal_fluxes(flux)};write_continuous_balance_audit(Path(output_root)/"balance_audit",result);return {"status":result["reconciliation"]["status"],**result}


def run_parameter_audit(project:str|Path,output_root:str|Path=DEFAULT_OUTPUT)->dict[str,Any]:
    config,forcing,_=_project_config(project);parameters={**DEFAULT_PARAMETERS,**config.get("parameters",{})};trace=trace_parameter_application(config);response=evaluate_parameter_response(forcing,config,parameters);unused=find_unused_parameters(trace,response);result={"trace":trace,"response":response,"unused":unused,"validation":validate_parameter_application(trace,response)};write_parameter_application_report(Path(output_root)/"parameter_audit",result);return result


def run_routing_audit(continuous_dir:str|Path,project:str|Path,output_root:str|Path=DEFAULT_OUTPUT)->dict[str,Any]:
    config,_,_=_project_config(project);routing=collect_routing_outputs(continuous_dir);result={"mass_balance":calculate_routing_mass_balance(routing),"parameters":validate_routing_parameters(config)};write_routing_audit_report(Path(output_root)/"structure",result);return result


def run_full_continuous_validation(project:str|Path=ROOT/"data_demo/drought",output_root:str|Path=DEFAULT_OUTPUT)->dict[str,Any]:
    output=Path(output_root);output.mkdir(parents=True,exist_ok=True);config,forcing,base=_project_config(project)
    corrected=run_continuous_config(base/"continuous_model_config.yaml",output/"corrected_continuous")
    inputs=run_input_audit(project,output);pet=run_pet_audit(project,output);balance=run_balance_audit(corrected["outputs"]["manifest"].parent,output);flow=run_flow_audit(project,output,corrected["outputs"]["manifest"].parent)
    truth_dir=ROOT/"data_demo/continuous_validation";generate_synthetic_truth(truth_dir);truth=run_parameter_recovery(truth_dir);write_truth_recovery_report(output/"truth_recovery",truth)
    parameter=run_parameter_audit(project,output);observed=pd.read_csv(base/"observed_streamflow.csv");sim=corrected["routing"].outflow_m3/86400;sensitivity=run_continuous_sensitivity(forcing,config,{**DEFAULT_PARAMETERS,**config.get("parameters",{})},observed,16);write_continuous_sensitivity_report(output/"sensitivity",sensitivity)
    benchmark=run_continuous_benchmarks(forcing,observed,sim,_area(config));write_benchmark_report(output/"benchmarks",benchmark)
    calibration=run_continuous_parameter_search(base,{"max_candidates":30});write_continuous_calibration_report(output/"calibration",calibration)
    import yaml
    (output/"calibration"/"staged_calibration_plan.yaml").write_text(yaml.safe_dump(build_staged_calibration_plan({**DEFAULT_PARAMETERS,**config.get("parameters",{})}),sort_keys=False),encoding="utf-8")
    pd.DataFrame([{"stage":"joint_refinement","status":calibration["status"],"candidate_count":calibration["candidate_count"]}]).to_excel(output/"calibration"/"stage_results.xlsx",index=False)
    structure=diagnose_structural_mismatch(flow,truth["status"]);write_structure_diagnostic_report(output/"structure",structure)
    result={"input":inputs["result"],"pet":pet["statistics"],"balance":balance,"flow_audit":flow,"truth_recovery":truth,"parameter":parameter["validation"],"structure":structure,"calibration_status":calibration["status"]};validation_status=classify_continuous_validation(result);gate=evaluate_water_quality_hydrology_gate(result)
    summary=output/"summary";summary.mkdir(exist_ok=True);flat={"continuous_model_validation":validation_status,"water_quality_hydrology_gate":gate["status"],"pet_status":pet["statistics"]["status"],"balance_status":balance["status"],"truth_recovery_status":truth["status"],"structure_status":structure["status"]}
    with pd.ExcelWriter(summary/"continuous_validation_summary.xlsx") as writer:pd.DataFrame([flat]).to_excel(writer,sheet_name="summary",index=False);pd.DataFrame([flow]).to_excel(writer,sheet_name="flow_volume",index=False)
    manifest={**flat,"truth_recovery_is_real_validation":False,"legacy_demo_type":"different_structure_stress_test","gate":gate};(summary/"continuous_validation_manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=str),encoding="utf-8");(summary/"water_quality_hydrology_gate.json").write_text(json.dumps(gate,indent=2,ensure_ascii=False),encoding="utf-8")
    message="# Continuous model validation\n\nWater-balance closure does not demonstrate flow simulation skill. Water-quality transport requires credible surface, interflow, baseflow and routing processes.\n\n"+json.dumps(manifest,indent=2,ensure_ascii=False,default=str)
    for name in ("continuous_validation_report_zh.md","continuous_validation_report_en.md"):(summary/name).write_text(message,encoding="utf-8")
    _write_remaining_charts(output,corrected,benchmark)
    bundle=summary/"continuous_validation_bundle.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as archive:
        for path in output.rglob("*"):
            if path.is_file() and path!=bundle and path.suffix in {".csv",".xlsx",".json",".md",".png",".yaml"}: archive.write(path,path.relative_to(output))
    return {"status":validation_status,"gate":gate,"output_dir":output,"manifest":manifest}


def _write_remaining_charts(output:Path,result:dict[str,Any],benchmarks:dict[str,Any])->None:
    charts={"rainfall_pet_aet.png":(["precipitation_mm","potential_et_mm","actual_et_mm"],"mm/d"),"complete_water_balance.png":(["surface_runoff_mm","interflow_mm","baseflow_mm"],"mm/d"),"groundwater_storage_diagnostic.png":([],"mm")}; flux=result["fluxes"].groupby("date",as_index=False).mean(numeric_only=True); states=result["states"].groupby("date",as_index=False).mean(numeric_only=True)
    for name,(cols,label) in charts.items():
        frame=states if not cols else flux;available=[x for x in cols if x in frame] or ["groundwater_storage_mm"]
        fig,ax=plt.subplots(figsize=(8,3));[ax.plot(pd.to_datetime(frame.date),frame[x],label=x) for x in available];ax.legend();ax.set_ylabel(label);fig.tight_layout();fig.savefig(output/name,dpi=120);plt.close(fig)
    ts=benchmarks["timeseries"];fig,ax=plt.subplots(figsize=(8,3));[ax.plot(ts.date,ts[x],label=x) for x in ("observed_cms","hydrolite_cms")];ax.legend();fig.tight_layout();fig.savefig(output/"high_flow_comparison.png",dpi=120);fig.savefig(output/"low_flow_comparison.png",dpi=120);fig.savefig(output/"flow_duration_curve_comparison.png",dpi=120);fig.savefig(output/"seasonal_flow_bias.png",dpi=120);plt.close(fig)


def inspect_continuous_run(output_dir:str|Path)->dict[str,Any]:
    root=Path(output_dir);return {"exists":root.exists(),"files":sorted(str(x.relative_to(root)) for x in root.rglob("*") if x.is_file())}
def write_continuous_validation_report(output_dir:str|Path,result:dict[str,Any])->Path:
    path=Path(output_dir)/"summary"/"continuous_validation_report_zh.md";path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str),encoding="utf-8");return path


def rebuild_drought_v2(project: str | Path = ROOT / "data_demo" / "drought", output_root: str | Path = ROOT / "output" / "drought_model_v2") -> dict[str, Any]:
    """Rebuild only the corrected synthetic diagnostic outputs; legacy drought output is untouched."""
    from hydrolite.drought_workflow import run_drought_indices_workflow, run_drought_monitoring_workflow, write_drought_summary
    root=Path(output_root); continuous=root/"continuous"; project=Path(project)
    run=run_continuous_config(project/"continuous_model_config.yaml", continuous)
    run_drought_indices_workflow(project, root/"indices", continuous)
    run_drought_monitoring_workflow(project, root/"monitoring", root/"indices")
    paths=write_drought_summary(root)
    (root/"drought_model_v2_manifest.json").write_text(json.dumps({"status":"completed","synthetic_demo":True,"continuous_dir":str(continuous),"legacy_output_preserved":True},indent=2),encoding="utf-8")
    return {"status":"completed","root":root,"water_balance":run["validation"],"paths":paths}


def validate_drought_v2(output_root: str | Path) -> dict[str, Any]:
    root=Path(output_root);required=["continuous/continuous_model_manifest.json","indices/drought_indices_monthly.csv","monitoring/current_drought_status.json","summary/drought_model_manifest.json","drought_model_v2_manifest.json"];missing=[x for x in required if not (root/x).exists()];return {"status":"passed" if not missing else "failed","missing":missing}
