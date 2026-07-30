from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import yaml

from hydrolite.continuous_calibration import run_continuous_parameter_search, write_continuous_calibration_report
from hydrolite.continuous_hydrology import (
    DEFAULT_OUTPUT as CONTINUOUS_OUTPUT,
    create_continuous_model_config,
    load_continuous_model_config,
    run_continuous_config,
    validate_continuous_model_config,
    validate_continuous_water_balance,
)
from hydrolite.drought_classification import classify_drought_components
from hydrolite.drought_forecast import (
    load_drought_forecast_config,
    run_drought_forecast_ensemble,
    validate_drought_forecast_config,
    write_drought_forecast_report,
)
from hydrolite.drought_lstm import assess_drought_lstm_readiness, run_drought_lstm_synthetic_smoke_test
from hydrolite.drought_ml import assess_drought_ml_readiness, run_drought_ml_synthetic_demo
from hydrolite.drought_workflow import (
    DEFAULT_ROOT,
    DEMO_PROJECT,
    assess_drought_readiness,
    create_drought_demo_scenarios,
    diagnose_drought_dependencies,
    export_drought_model_bundle,
    run_drought_assimilation_workflow,
    run_drought_events_workflow,
    run_drought_forecast_demo,
    run_drought_indices_workflow,
    run_drought_monitoring_workflow,
    run_drought_uncertainty_workflow,
    validate_drought_model,
    write_drought_summary,
)
from hydrolite.model_warmup import (
    calculate_required_warmup,
    create_warmup_forcing,
    run_warmup,
    validate_warmup_result,
    write_warmup_report,
)


def register_drought_cli(subparsers) -> None:
    continuous = subparsers.add_parser("continuous", help="Daily continuous hydrology MVP.")
    child = continuous.add_subparsers(dest="continuous_command", required=True)
    item = child.add_parser("create-config"); item.add_argument("project")
    item = child.add_parser("validate-config"); item.add_argument("config")
    item = child.add_parser("warmup"); item.add_argument("config")
    item = child.add_parser("run"); item.add_argument("config")
    item = child.add_parser("balance"); item.add_argument("output")
    item = child.add_parser("calibrate"); item.add_argument("project")
    item = child.add_parser("validate"); item.add_argument("output")

    drought = subparsers.add_parser("drought", help="Drought monitoring and scenario forecast MVP.")
    child = drought.add_subparsers(dest="drought_command", required=True)
    for name in ("diagnose", "dependencies", "scenario-demo", "forecast-demo", "ml-demo", "lstm-smoke"):
        child.add_parser(name)
    for name in ("readiness", "indices", "events", "monitor", "assimilation", "ml-readiness", "lstm-readiness"):
        item = child.add_parser(name); item.add_argument("workspace")
    item = child.add_parser("classify"); item.add_argument("output")
    item = child.add_parser("forecast"); item.add_argument("project"); item.add_argument("config")
    item = child.add_parser("uncertainty"); item.add_argument("output")
    for name in ("report", "bundle", "validate"):
        item = child.add_parser(name); item.add_argument("output")


def _load_continuous_output(output: str | Path) -> dict:
    root = Path(output)
    return {
        "fluxes": pd.read_csv(root / "daily_fluxes.csv"),
        "states": pd.read_csv(root / "daily_states.csv"),
        "routing": pd.read_csv(root / "daily_routing.csv"),
    }


def run_drought_cli(args) -> int:
    if args.command == "continuous":
        command = args.continuous_command
        if command == "create-config":
            print(create_continuous_model_config(args.project)); return 0
        if command == "validate-config":
            result = validate_continuous_model_config(load_continuous_model_config(args.config))
            print(json.dumps(result, indent=2, ensure_ascii=False)); return 0 if result["status"] == "passed" else 1
        if command == "run":
            result = run_continuous_config(args.config)
            print(json.dumps({"status":result["validation"]["status"],"output":str(CONTINUOUS_OUTPUT),"water_balance":result["water_balance"]},indent=2)); return 0 if result["validation"]["status"]=="passed" else 1
        if command == "warmup":
            config = load_continuous_model_config(args.config); base=Path(config["_config_path"]).parent
            forcing=pd.read_csv(base/config["input"]["daily_meteorology_csv"])
            assessment=calculate_required_warmup(config,forcing);warmup_forcing=create_warmup_forcing(forcing,assessment["warmup_days"])
            from hydrolite.continuous_hydrology import DEFAULT_PARAMETERS, initialize_continuous_state, run_continuous_period
            result=run_warmup(run_continuous_period,warmup_forcing,initialize_continuous_state(config),{**DEFAULT_PARAMETERS,**config.get("parameters",{})},config)
            result["source"]=config.get("warmup",{}).get("method");write_warmup_report(CONTINUOUS_OUTPUT,result)
            print(json.dumps({**assessment,"validation":validate_warmup_result(result)},indent=2));return 0
        if command in {"balance","validate"}:
            result=_load_continuous_output(args.output);validation=validate_continuous_water_balance(result)
            print(json.dumps(validation,indent=2));return 0 if validation["status"]=="passed" else 1
        if command == "calibrate":
            project=Path(args.project);result=run_continuous_parameter_search(project,{"max_candidates":30})
            write_continuous_calibration_report(DEFAULT_ROOT/"calibration",result)
            print(json.dumps({key:value for key,value in result.items() if key!="results"},indent=2,default=str));return 0 if result["status"] in {"completed","framework_ready_real_data_missing","insufficient_data"} else 1
    command=args.drought_command
    if command in {"diagnose","dependencies"}:
        print(json.dumps(diagnose_drought_dependencies(),indent=2,default=str));return 0
    if command=="readiness":
        print(json.dumps(assess_drought_readiness(args.workspace),indent=2));return 0
    if command=="indices":
        result=run_drought_indices_workflow(args.workspace);print(json.dumps({"status":"completed","records":len(result["monthly"]),"paths":{key:str(value) for key,value in result["paths"].items()}},indent=2));return 0
    if command=="events":
        result=run_drought_events_workflow(args.workspace);print(json.dumps({"status":result["status"],"events":len(result["catalog"])},indent=2));return 0
    if command=="monitor":
        result=run_drought_monitoring_workflow(args.workspace);print(json.dumps({key:value for key,value in result.items() if key not in {"components","paths"}},indent=2,default=str));return 0
    if command=="classify":
        root=Path(args.output);source=root/"drought_indices_monthly.csv";data=pd.read_csv(source);classified=classify_drought_components(data)
        classified.to_excel(root/"drought_classification.xlsx",index=False);print(root/"drought_classification.xlsx");return 0
    if command=="scenario-demo":
        ensemble=create_drought_demo_scenarios();print(json.dumps({"status":"completed","members":int(ensemble.member_id.nunique()),"mode":"scenario_simulation"},indent=2));return 0
    if command=="forecast-demo":
        result=run_drought_forecast_demo();print(json.dumps({"status":result["status"],"mode":result["mode"],"members":result["member_count"],"successful_members":result["successful_members"],"lead_months":result["lead_months"]},indent=2));return 0 if result["status"]=="completed" else 1
    if command=="forecast":
        config=load_drought_forecast_config(args.config);check=validate_drought_forecast_config(config)
        if check["status"]!="passed": print(json.dumps(check,indent=2));return 1
        ensemble=create_drought_demo_scenarios(args.project)
        result=run_drought_forecast_ensemble(args.project,ensemble,config);result["forcing_members"]=ensemble;ensemble.to_csv(DEFAULT_ROOT/"forecast"/"forcing_members.csv",index=False);write_drought_forecast_report(DEFAULT_ROOT/"forecast",result)
        print(json.dumps({"status":result["status"],"mode":result["mode"],"members":result["member_count"]},indent=2));return 0 if result["status"]=="completed" else 1
    if command=="uncertainty":
        result=run_drought_uncertainty_workflow(args.output);print(json.dumps({"status":"completed","quantile_rows":len(result["quantiles"]),"probability_label":result["probability_label"]},indent=2));return 0
    if command=="assimilation":
        result=run_drought_assimilation_workflow(args.workspace);print(json.dumps({"status":result["status"],"adjustments":len(result["adjustments"])},indent=2));return 0
    if command=="ml-readiness":
        source=Path(args.workspace)/"daily_meteorology.csv";result=assess_drought_ml_readiness(source if source.exists() else pd.DataFrame())
        (DEFAULT_ROOT/"ml").mkdir(parents=True,exist_ok=True);(DEFAULT_ROOT/"ml"/"ml_readiness.json").write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2));return 0
    if command=="ml-demo":
        result=run_drought_ml_synthetic_demo(DEFAULT_ROOT/"ml");print(json.dumps({key:value for key,value in result.items() if key!="metrics"},indent=2,default=str));return 0
    if command=="lstm-readiness":
        source=Path(args.workspace)/"daily_meteorology.csv";result=assess_drought_lstm_readiness(source if source.exists() else None);print(json.dumps(result,indent=2));return 0
    if command=="lstm-smoke":
        result=run_drought_lstm_synthetic_smoke_test(DEFAULT_ROOT/"lstm");print(json.dumps(result,indent=2));return 0
    if command=="report":
        print(json.dumps({key:str(value) for key,value in write_drought_summary(args.output).items()},indent=2));return 0
    if command=="bundle":
        print(export_drought_model_bundle(args.output));return 0
    if command=="validate":
        result=validate_drought_model(args.output);print(json.dumps(result,indent=2));return 0 if result["status"]=="passed" else 1
    return 2
