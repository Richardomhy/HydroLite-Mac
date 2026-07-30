from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import importlib.metadata
import importlib.util
import json
import platform
import shutil
import sys
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from hydrolite.continuous_hydrology import DEFAULT_OUTPUT as CONTINUOUS_OUTPUT, load_continuous_model_config, run_continuous_config, validate_continuous_water_balance
from hydrolite.drought_assimilation import run_drought_state_assimilation, write_drought_assimilation_report
from hydrolite.drought_classification import classify_drought_components
from hydrolite.drought_events import build_drought_event_catalog, write_drought_event_report
from hydrolite.drought_forecast import DEFAULT_OUTPUT as FORECAST_OUTPUT, load_drought_forecast_config, run_drought_forecast_ensemble, write_drought_forecast_report
from hydrolite.drought_indices import (
    DEFAULT_SCALES, calculate_composite_drought_index, calculate_groundwater_percentile,
    calculate_reservoir_storage_percentile, calculate_runoff_percentile,
    calculate_soil_moisture_percentile, calculate_spei, calculate_spi, calculate_ssi,
    write_drought_index_report,
)
from hydrolite.drought_lstm import assess_drought_lstm_readiness, run_drought_lstm_synthetic_smoke_test
from hydrolite.drought_ml import assess_drought_ml_readiness, run_drought_ml_synthetic_demo
from hydrolite.drought_monitoring import (
    assess_current_agricultural_drought, assess_current_groundwater_drought,
    assess_current_hydrological_drought, assess_current_meteorological_drought,
    assess_current_reservoir_drought, calculate_current_composite_status,
    write_current_drought_status,
)
from hydrolite.drought_scenarios import (
    create_pet_scenarios, create_precipitation_scale_scenarios, create_season_shift_scenarios,
    create_temperature_scenarios, write_drought_scenario_report,
)
from hydrolite.drought_uncertainty import (
    calculate_drought_class_fraction, calculate_duration_distribution,
    calculate_index_quantiles, calculate_onset_time_distribution,
    calculate_recovery_time_distribution, calculate_severity_distribution,
    classify_drought_uncertainty_sources, write_drought_uncertainty_report,
)
from hydrolite.evapotranspiration import calculate_hargreaves_et


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "output" / "drought_model"
DEMO_PROJECT = ROOT / "data_demo" / "drought"
SCIENCE_PACKAGES = (
    "numpy", "pandas", "scipy", "xarray", "netCDF4", "h5py", "cftime",
    "scikit-learn", "joblib", "pyproj", "shapely", "cdsapi", "earthaccess",
    "pystac-client", "fsspec", "rasterio", "geopandas",
)


def diagnose_drought_dependencies(output_dir: str | Path = DEFAULT_ROOT / "environment") -> dict[str, Any]:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    packages = []
    for name in SCIENCE_PACKAGES:
        import_name = {"scikit-learn":"sklearn","pystac-client":"pystac_client"}.get(name, name)
        available = importlib.util.find_spec(import_name) is not None
        try: version = importlib.metadata.version(name) if available else None
        except importlib.metadata.PackageNotFoundError: version = None
        packages.append({"package":name,"available":available,"version":version,"required_for_core":name in {"numpy","pandas","scipy"}})
    result = {
        "status":"available" if all(row["available"] for row in packages if row["required_for_core"]) else "degraded",
        "python":sys.version.split()[0],"executable":sys.executable,"platform":platform.platform(),
        "conda_environment":Path(sys.prefix).name if "conda" in sys.version.lower() or Path(sys.prefix,"conda-meta").exists() else None,
        "packages":packages,
    }
    (output/"dependency_diagnosis.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    (output/"dependency_diagnosis.md").write_text("# HydroLite science dependency diagnosis\n\n```text\n"+pd.DataFrame(packages).to_string(index=False)+"\n```\n",encoding="utf-8")
    return result


def assess_drought_readiness(workspace: str | Path) -> dict[str, Any]:
    root=Path(workspace)
    required=["daily_meteorology.csv","continuous_model_config.yaml","drought_index_config.yaml","drought_forecast_config.yaml"]
    missing=[name for name in required if not (root/name).exists()]
    expected=root/"expected_results.json"
    synthetic=bool(json.loads(expected.read_text()).get("synthetic_demo")) if expected.exists() else False
    return {"status":"framework_ready" if not missing else "missing_data","missing":missing,"synthetic_demo":synthetic,"capability_level":"synthetic_demo" if synthetic and not missing else "framework_ready_real_data_missing"}


def _continuous(project: Path = DEMO_PROJECT):
    manifest=CONTINUOUS_OUTPUT/"continuous_model_manifest.json"
    if not manifest.exists(): return run_continuous_config(project/"continuous_model_config.yaml")
    return None


def run_drought_indices_workflow(project_dir: str | Path, output_dir: str | Path = DEFAULT_ROOT / "indices") -> dict[str, Any]:
    project=Path(project_dir);_continuous(project)
    flux=pd.read_csv(CONTINUOUS_OUTPUT/"daily_fluxes.csv",parse_dates=["date"])
    states=pd.read_csv(CONTINUOUS_OUTPUT/"daily_states.csv",parse_dates=["date"])
    routing=pd.read_csv(CONTINUOUS_OUTPUT/"daily_routing.csv",parse_dates=["date"])
    daily=flux.merge(states[["date","subbasin_id","upper_soil_storage_mm","lower_soil_storage_mm","groundwater_storage_mm","reservoir_storage_m3"]],on=["date","subbasin_id"])
    daily["soil_moisture_mm"]=daily["upper_soil_storage_mm"]+daily["lower_soil_storage_mm"]
    aggregate=daily.groupby("date",as_index=False).mean(numeric_only=True).merge(routing[["date","outflow_m3"]],on="date")
    aggregate["streamflow_cms"]=aggregate["outflow_m3"]/86400
    monthly=aggregate.set_index("date").resample("MS").agg({
        "precipitation_mm":"sum","potential_et_mm":"sum","actual_et_mm":"sum",
        "soil_moisture_mm":"mean","groundwater_storage_mm":"mean","reservoir_storage_m3":"mean",
        "streamflow_cms":"mean","surface_runoff_mm":"sum","baseflow_mm":"sum",
    })
    cfg=yaml.safe_load((project/"drought_index_config.yaml").read_text())
    baseline=tuple(cfg.get("baseline_period",[])) or None;scales=cfg.get("scales_months",DEFAULT_SCALES);metadata=[]
    for scale in scales:
        for name,series in (
            (f"SPI_{scale}",calculate_spi(monthly["precipitation_mm"],scale,baseline,cfg.get("distributions",{}).get("SPI","gamma"))),
            (f"SPEI_{scale}",calculate_spei(monthly["precipitation_mm"],monthly["potential_et_mm"],scale,baseline,cfg.get("distributions",{}).get("SPEI","normal"))),
            (f"SSI_{scale}",calculate_ssi(monthly["streamflow_cms"],scale,baseline,cfg.get("distributions",{}).get("SSI","gamma"))),
        ):
            monthly[name]=series;metadata.append({"index":name,**series.attrs})
    monthly["soil_moisture_percentile"]=calculate_soil_moisture_percentile(monthly["soil_moisture_mm"],baseline)
    monthly["runoff_percentile"]=calculate_runoff_percentile(monthly["surface_runoff_mm"],baseline)
    monthly["groundwater_storage_percentile"]=calculate_groundwater_percentile(monthly["groundwater_storage_mm"],baseline)
    monthly["reservoir_storage_percentile"]=calculate_reservoir_storage_percentile(monthly["reservoir_storage_m3"],baseline)
    monthly["composite_drought_index"]=calculate_composite_drought_index(monthly[["SPI_12","SPEI_12","SSI_12"]],{"SPI_12":0.35,"SPEI_12":0.35,"SSI_12":0.30})
    monthly=monthly.reset_index()
    aggregate["soil_moisture_percentile"]=aggregate["soil_moisture_mm"].rank(pct=True)*100
    result={"daily":aggregate,"monthly":monthly,"metadata":metadata,"scales":scales,"indices":["precipitation anomaly","SPI","SPEI","SSI","soil moisture percentile","runoff percentile","groundwater percentile","reservoir percentile","composite drought index"],"baseline_period":baseline}
    paths=write_drought_index_report(output_dir,result)
    return {**result,"paths":paths}


def run_drought_events_workflow(project_dir: str | Path, output_dir: str | Path = DEFAULT_ROOT / "indices") -> dict[str, Any]:
    source=Path(output_dir)/"drought_indices_monthly.csv"
    if not source.exists(): run_drought_indices_workflow(project_dir,output_dir)
    data=pd.read_csv(source,parse_dates=["date"]).set_index("date")
    catalog=build_drought_event_catalog(data[["SPI_12","SPEI_12","SSI_12","composite_drought_index"]],threshold=-1,min_duration=2)
    paths=write_drought_event_report(output_dir,catalog)
    return {"status":"completed","catalog":catalog,"paths":paths}


def run_drought_monitoring_workflow(project_dir: str | Path, output_dir: str | Path = DEFAULT_ROOT / "monitoring") -> dict[str, Any]:
    source=DEFAULT_ROOT/"indices"/"drought_indices_monthly.csv"
    if not source.exists(): run_drought_indices_workflow(project_dir)
    data=pd.read_csv(source,parse_dates=["date"])
    components=[
        assess_current_meteorological_drought(data["SPEI_12"]),
        assess_current_agricultural_drought((data["soil_moisture_percentile"]-50)/25),
        assess_current_hydrological_drought(data["SSI_12"]),
        assess_current_reservoir_drought((data["reservoir_storage_percentile"]-50)/25),
        assess_current_groundwater_drought((data["groundwater_storage_percentile"]-50)/25),
    ]
    composite=calculate_current_composite_status(components)
    result={**composite,"analysis_date":str(data["date"].max().date()),"data_as_of":str(data["date"].max().date()),"latest_observation_date":str(data["date"].max().date()),"components":components,"confidence":"synthetic_demo_only","missing_sources":[],"maximum_latency_days":31}
    paths=write_current_drought_status(output_dir,result);return {**result,"paths":paths}


def create_drought_demo_scenarios(project_dir: str | Path = DEMO_PROJECT, output_dir: str | Path = FORECAST_OUTPUT) -> pd.DataFrame:
    source=pd.read_csv(Path(project_dir)/"daily_meteorology.csv",parse_dates=["date"])
    source=source[(source["date"]>="2019-01-01")&(source["date"]<="2019-12-31")].copy()
    baseline=source.assign(member_id="baseline",scenario_type="synthetic_demo")
    pet_source=source.copy()
    pet_source["potential_et_mm"]=calculate_hargreaves_et(pet_source,22.6)
    parts=[
        baseline,
        create_precipitation_scale_scenarios(source,[0.8,0.6]),
        create_temperature_scenarios(source,[1.0,2.0]),
        create_pet_scenarios(pet_source,[1.15]),
        create_season_shift_scenarios(source,[30]),
    ]
    dry=source.copy();dry["precipitation_mm"]*=0.5;dry["temperature_min_c"]+=1;dry["temperature_max_c"]+=1;dry["temperature_mean_c"]+=1;dry["member_id"]="dry_historical_analogue";dry["scenario_type"]="synthetic_demo";parts.append(dry)
    ensemble=pd.concat(parts,ignore_index=True)
    write_drought_scenario_report(output_dir,ensemble)
    return ensemble


def run_drought_forecast_demo(project_dir: str | Path = DEMO_PROJECT, output_dir: str | Path = FORECAST_OUTPUT) -> dict[str, Any]:
    _continuous(Path(project_dir));ensemble=create_drought_demo_scenarios(project_dir,output_dir)
    config=load_drought_forecast_config(Path(project_dir)/"drought_forecast_config.yaml")
    result=run_drought_forecast_ensemble(project_dir,ensemble,config)
    result["forcing_members"]=ensemble;ensemble.to_csv(Path(output_dir)/"forcing_members.csv",index=False)
    result["paths"]=write_drought_forecast_report(output_dir,result);return result


def run_drought_uncertainty_workflow(output_dir: str | Path = FORECAST_OUTPUT) -> dict[str, Any]:
    root=Path(output_dir);indices=pd.read_excel(root/"drought_class_members.xlsx",sheet_name="members")
    result={"quantiles":calculate_index_quantiles(indices),"class_fractions":calculate_drought_class_fraction(indices),"onset":calculate_onset_time_distribution(indices),"recovery":calculate_recovery_time_distribution(indices),"duration":calculate_duration_distribution(indices),"severity":calculate_severity_distribution(indices),"uncertainty_sources":classify_drought_uncertainty_sources({}),"probability_label":"scenario_member_fraction"}
    result["report"]=write_drought_uncertainty_report(root,result);return result


def run_drought_assimilation_workflow(project_dir: str | Path, output_dir: str | Path = DEFAULT_ROOT / "assimilation") -> dict[str, Any]:
    project=Path(project_dir);config=load_continuous_model_config(project/"continuous_model_config.yaml")
    from hydrolite.continuous_hydrology import initialize_continuous_state
    state=initialize_continuous_state(config)
    soil=pd.read_csv(project/"observed_soil_moisture.csv").tail(1)
    groundwater=pd.read_csv(project/"observed_groundwater.csv").tail(1)
    rows=[
        {"date":soil.iloc[0]["date"],"subbasin_id":"SB1","variable":"soil_moisture_mm","value":float(soil.iloc[0]["soil_moisture_fraction"])*380,"quality_status":"synthetic_demo"},
        {"date":groundwater.iloc[0]["date"],"subbasin_id":"SB1","variable":"groundwater_storage_mm","value":groundwater.iloc[0]["groundwater_storage_mm"],"quality_status":"synthetic_demo"},
    ]
    result=run_drought_state_assimilation(state,pd.DataFrame(rows),{"soil_moisture_gain":0.25,"groundwater_gain":0.2});result["method"]="soil_moisture_nudging + groundwater_state_update"
    result["paths"]=write_drought_assimilation_report(output_dir,result);return result


def write_drought_summary(output_root: str | Path = DEFAULT_ROOT) -> dict[str, Path]:
    root=Path(output_root);summary=root/"summary";summary.mkdir(parents=True,exist_ok=True)
    continuous=json.loads((root/"continuous/continuous_model_manifest.json").read_text()) if (root/"continuous/continuous_model_manifest.json").exists() else {}
    monitoring=json.loads((root/"monitoring/current_drought_status.json").read_text()) if (root/"monitoring/current_drought_status.json").exists() else {}
    forecast=json.loads((root/"forecast/drought_forecast_manifest.json").read_text()) if (root/"forecast/drought_forecast_manifest.json").exists() else {}
    capabilities=[
        {"capability":"continuous_hydrology","status":"partial"},{"capability":"drought_monitoring","status":"partial"},
        {"capability":"drought_forecast","status":"partial"},{"capability":"drought_data_assimilation","status":"partial"},
        {"capability":"flood_forecast","status":"partial"},{"capability":"water_quality","status":"planned"},
    ]
    with pd.ExcelWriter(summary/"drought_model_summary.xlsx") as writer:
        pd.DataFrame([continuous]).to_excel(writer,sheet_name="continuous",index=False)
        pd.DataFrame([monitoring]).to_excel(writer,sheet_name="monitoring",index=False)
        pd.DataFrame([forecast]).to_excel(writer,sheet_name="forecast",index=False)
    pd.DataFrame(capabilities).to_excel(summary/"drought_capability_status.xlsx",index=False)
    for language,name in (("zh","drought_model_report_zh.md"),("en","drought_model_report_en.md")):
        title="# HydroLite 干旱模型综合报告\n\n" if language=="zh" else "# HydroLite Drought Model Report\n\n"
        (summary/name).write_text(title+"Continuous hydrology, diagnostic drought indices, scenario ensembles and state assimilation are partial MVP capabilities. Synthetic demo results are not operational forecasts or statutory alerts.\n",encoding="utf-8")
    manifest={"status":"completed","capability_level":"synthetic_demo","continuous_water_balance":continuous.get("water_balance",{}).get("status"),"current_status":monitoring.get("class"),"forecast_mode":forecast.get("mode"),"generated_at":datetime.now(timezone.utc).isoformat()}
    (summary/"drought_model_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return {"summary":summary/"drought_model_summary.xlsx","capabilities":summary/"drought_capability_status.xlsx","report_zh":summary/"drought_model_report_zh.md","report_en":summary/"drought_model_report_en.md","manifest":summary/"drought_model_manifest.json"}


def export_drought_model_bundle(output_root: str | Path = DEFAULT_ROOT) -> Path:
    root=Path(output_root);summary=root/"summary";summary.mkdir(parents=True,exist_ok=True);bundle=summary/"drought_model_bundle.zip"
    allowed={".csv",".xlsx",".json",".md",".png",".yaml"}
    forbidden_parts={"data_raw","external","runtime","raw","standardized"}
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path!=bundle and path.suffix.lower() in allowed and not forbidden_parts.intersection(path.parts) and path.stat().st_size<20_000_000:
                archive.write(path,path.relative_to(root))
    return bundle


def validate_drought_model(output_root: str | Path = DEFAULT_ROOT) -> dict[str, Any]:
    root=Path(output_root)
    required=[
        "continuous/daily_water_balance.csv","continuous/continuous_model_manifest.json",
        "indices/drought_indices_monthly.csv","indices/drought_event_catalog.xlsx",
        "monitoring/current_drought_status.json","forecast/drought_forecast_manifest.json",
        "assimilation/assimilation_adjustments.csv","summary/drought_model_manifest.json",
    ]
    missing=[name for name in required if not (root/name).exists()]
    gate=None
    if (root/"continuous/continuous_model_manifest.json").exists():
        gate=json.loads((root/"continuous/continuous_model_manifest.json").read_text()).get("water_balance",{}).get("status")
    return {"status":"passed" if not missing and gate=="passed" else "failed","missing":missing,"continuous_water_balance_gate":gate}
