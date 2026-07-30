"""Explicit partial water and soil/sediment accounting ledger."""
from __future__ import annotations
import json, zipfile
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def _path(v:str|Path)->Path:return Path(v).expanduser().resolve()
def collect_watershed_accounting_components(project_dir:str|Path,config:dict|None=None)->dict[str,Any]:
    project=_path(project_dir);base=project/"output/qgis_demo/result_flow.csv";cons=ROOT/"output/conservation/conservation_summary.xlsx";rusle=ROOT/"output/rusle/subbasin_soil_loss.xlsx"
    runoff=float(pd.read_csv(base)["outflow_cms"].sum()*3600) if base.exists() else None
    retention=float(pd.read_excel(cons).iloc[0].get("water_retention_amount_m3_event")) if cons.exists() else None
    soil=pd.read_excel(rusle).iloc[0].to_dict() if rusle.exists() else {}
    return {"surface_runoff":runoff,"water_conservation_amount":retention,"soil":soil}
def build_water_accounting_ledger(components:dict[str,Any])->pd.DataFrame:
    rows=[("precipitation_input",None,"missing"),("surface_runoff",components.get("surface_runoff"),"available" if components.get("surface_runoff") is not None else "missing"),("HEC-HMS outlet runoff",None,"available_reference_only"),("HydroLite outlet runoff",components.get("surface_runoff"),"available" if components.get("surface_runoff") is not None else "missing"),("infiltration_or_loss",None,"missing"),("evapotranspiration",None,"missing"),("baseflow",None,"missing"),("groundwater_exchange",None,"missing"),("waterbody_storage_change",None,"missing"),("channel_storage_change",None,"missing"),("water_conservation_amount",components.get("water_conservation_amount"),"available" if components.get("water_conservation_amount") is not None else "missing"),("observed_discharge",None,"missing"),("residual",None,"partial")]
    return pd.DataFrame(rows,columns=["component","value","status"])
def build_soil_sediment_accounting_ledger(components:dict[str,Any])->pd.DataFrame:
    soil=components.get("soil") or {};rows=[("RUSLE hillslope soil loss",soil.get("baseline_total_t_yr"),"available" if soil else "missing"),("conservation soil reduction",soil.get("soil_conservation_t_yr"),"available" if soil else "missing"),("sediment delivery ratio",None,"planned"),("delivered sediment",None,"missing"),("channel erosion",None,"missing"),("bank erosion",None,"missing"),("gully erosion",None,"missing"),("reservoir trapping",None,"missing"),("outlet sediment load",None,"missing"),("observed sediment",None,"missing"),("residual",None,"partial")];return pd.DataFrame(rows,columns=["component","value","status"])
def assess_accounting_completeness(ledger:pd.DataFrame)->str:return "partial" if (ledger["status"].isin(["missing","planned","partial"])).any() else "substantial"
def calculate_water_balance_residual(ledger:pd.DataFrame):return None
def calculate_sediment_accounting_residual(ledger:pd.DataFrame):return None
def write_accounting_completeness_matrix(output_dir:str|Path,result:dict[str,Any])->Path:
    p=_path(output_dir)/"accounting_completeness_matrix.xlsx";pd.DataFrame([{"water_status":result["water_status"],"soil_sediment_status":result["soil_sediment_status"],"accounting_status":result["accounting_status"]}]).to_excel(p,index=False);return p
def write_watershed_accounting_report(output_dir:str|Path,result:dict[str,Any])->dict[str,Path]:
    root=_path(output_dir);zh=root/"watershed_accounting_report_zh.md";en=root/"watershed_accounting_report_en.md";zh.write_text("# 流域综合核算\n\n当前状态为 partial；缺失项保持空值，不作为零。完整核算仍需 ET、地下水、蓄变量、观测流量、泥沙输移与验证。\n");en.write_text("# Watershed accounting\n\nStatus is partial; missing items remain blank, never zero.\n");return {"zh":zh,"en":en}
def export_watershed_accounting_bundle(output_dir:str|Path)->Path:
    root=_path(output_dir);bundle=root/"watershed_accounting_bundle.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        for p in root.glob("*"):
            if p.is_file() and not any(x in p.name.lower() for x in ("secret","credential",".h5",".hdf",".dss")):z.write(p,p.name)
    return bundle
def build_watershed_accounting(project_dir:str|Path,output_dir:str|Path=ROOT/"output/watershed_accounting")->dict[str,Any]:
    root=_path(output_dir);root.mkdir(parents=True,exist_ok=True);c=collect_watershed_accounting_components(project_dir);water=build_water_accounting_ledger(c);soil=build_soil_sediment_accounting_ledger(c);water.to_excel(root/"water_accounting_ledger.xlsx",index=False);soil.to_excel(root/"soil_sediment_accounting_ledger.xlsx",index=False);result={"water":water,"soil":soil,"water_status":assess_accounting_completeness(water),"soil_sediment_status":assess_accounting_completeness(soil),"accounting_status":"partial"};write_accounting_completeness_matrix(root,result);reports=write_watershed_accounting_report(root,result);(root/"accounting_manifest.json").write_text(json.dumps({"accounting_status":"partial","reports":{k:v.name for k,v in reports.items()}},indent=2));return result
def validate_watershed_accounting(output_dir:str|Path)->dict[str,Any]:
    root=_path(output_dir);need=["water_accounting_ledger.xlsx","soil_sediment_accounting_ledger.xlsx","accounting_completeness_matrix.xlsx","accounting_manifest.json","watershed_accounting_report_zh.md","watershed_accounting_report_en.md"];missing=[x for x in need if not(root/x).exists()];return {"status":"passed" if not missing else "failed","missing":missing}
