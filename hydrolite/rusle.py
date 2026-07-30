"""Small local RUSLE MVP for annual average sheet and rill soil loss."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from hydrolite.watershed import _read_ascii_grid, _write_ascii_grid

ROOT=Path(__file__).resolve().parents[1]
def _path(v: str|Path)->Path:return Path(v).expanduser().resolve()
def detect_rusle_backends()->dict[str,Any]: return {"status":"available","backend":"numpy_ascii_grid","qgis_process_optional":False,"limitations":["No raster reprojection; all supplied factors must share a projected grid."]}
def inspect_rusle_input(path: str|Path)->dict[str,Any]:
    p=_path(path)
    if not p.exists(): return {"status":"missing","path":str(p)}
    if p.suffix.lower()==".asc":
        g=_read_ascii_grid(p);return {"status":"inspected","path":str(p),"shape":[g["nrows"],g["ncols"]],"cellsize":g["cellsize"],"crs":"projected_demo"}
    return {"status":"scalar_or_table","path":str(p)}
def load_rusle_factor(path_or_value: str|Path|float, factor_name:str)->dict[str,Any]:
    if isinstance(path_or_value,(int,float)): return {"factor_name":factor_name,"data":np.array(float(path_or_value)),"metadata":{"source":"user_scalar","unit":"dimensionless","crs":"not_applicable","confidence":"user_supplied"}}
    p=_path(path_or_value);g=_read_ascii_grid(p);return {"factor_name":factor_name,"data":np.array(g["values"],dtype=float),"grid":g,"metadata":{"source":str(p),"source_date":"","unit":"factor","spatial_resolution":g["cellsize"],"crs":"projected_demo","nodata":g["nodata_value"],"value_range":[float(np.nanmin(g["values"])),float(np.nanmax(g["values"]))],"processing_method":"provided","confidence":"synthetic_demo","warnings":[]}}
def validate_rusle_factor(factor:dict[str,Any],factor_name:str)->dict[str,Any]:
    values=np.asarray(factor["data"],dtype=float);ok=np.isfinite(values).all() and (values>=0).all() and not (factor_name in {"C","P"} and (values>1).any())
    return {"status":"passed" if ok else "failed","factor_name":factor_name,"min":float(np.nanmin(values)),"max":float(np.nanmax(values))}
def align_rusle_factors(factors:dict[str,dict[str,Any]],reference_grid:dict[str,Any]|None=None)->dict[str,dict[str,Any]]:
    shapes={np.asarray(v["data"]).shape for v in factors.values()}
    if len(shapes)>1: raise ValueError("RUSLE factor grids have mismatched shape; explicit alignment is required.")
    return factors
def calculate_rusle_soil_loss(r:Any,k:Any,ls:Any,c:Any,p:Any)->np.ndarray:return np.asarray(r)*np.asarray(k)*np.asarray(ls)*np.asarray(c)*np.asarray(p)
def calculate_soil_conservation_amount(baseline_loss:Any,scenario_loss:Any)->np.ndarray:return np.asarray(baseline_loss)-np.asarray(scenario_loss)
def classify_rusle_erosion_intensity(soil_loss:Any,classification:dict[float,str]|None=None)->np.ndarray:
    return np.select([np.asarray(soil_loss)<5,np.asarray(soil_loss)<25,np.asarray(soil_loss)<50],["slight","moderate","high"],default="very_high")
def calculate_rusle_statistics(soil_loss:Any,zones:Any=None)->pd.DataFrame:
    a=np.asarray(soil_loss,dtype=float);valid=np.isfinite(a);return pd.DataFrame([{"subbasin_id":"all","area_ha":float(a.size),"valid_area_ha":float(valid.sum()),"coverage_percent":float(valid.mean()*100),"mean_soil_loss_t_ha_yr":float(np.nanmean(a)),"median_soil_loss_t_ha_yr":float(np.nanmedian(a)),"maximum_soil_loss_t_ha_yr":float(np.nanmax(a)),"total_soil_loss_t_yr":float(np.nansum(a)),"uncertainty_status":"synthetic_demo","warnings":"not delivered sediment"}])
def calculate_ls_factor_from_dem(dem_path:str|Path,output_dir:str|Path,method:str="desmet_govers")->dict[str,Any]:
    g=_read_ascii_grid(dem_path)
    if g["cellsize"]<=0: raise ValueError("LS requires projected DEM pixel size in metres.")
    arr=np.asarray(g["values"],dtype=float);ls=np.maximum(.01,(arr.max()-arr+1)/max(arr.ptp(),1));out=_path(output_dir)/"ls_factor.asc";_write_ascii_grid(out,{**g,"values":ls.tolist()});return {"status":"partial","path":str(out),"method":method}
def validate_ls_factor(ls:Any,dem_metadata:dict[str,Any])->dict[str,Any]: return {"status":"passed" if np.isfinite(np.asarray(ls)).all() and dem_metadata.get("cellsize",0)>0 else "failed"}
def write_ls_diagnosis(output_dir:str|Path,result:dict[str,Any])->Path:p=_path(output_dir)/"ls_diagnosis.md";p.parent.mkdir(parents=True,exist_ok=True);p.write_text("# LS diagnosis\n\npartial MVP; projected DEM required.\n");return p
def _write_grid(path:Path,array:np.ndarray,grid:dict[str,Any])->Path:_write_ascii_grid(path,{**grid,"values":array.tolist()});return path
def run_rusle(config_path:str|Path,output_dir:str|Path)->dict[str,Any]:
    config_file=_path(config_path);cfg=yaml.safe_load(config_file.read_text()) or {};root=_path(output_dir);root.mkdir(parents=True,exist_ok=True)
    factors={name:load_rusle_factor(config_file.parent/value,name) for name,value in (cfg.get("factors") or {}).items() if name in {"R","K","LS","C_baseline","C_conservation","P_baseline","P_conservation"}}
    required={"R","K","LS","C_baseline","C_conservation","P_baseline","P_conservation"}
    if required-set(factors): raise ValueError("Missing RUSLE factors; missing factors are not defaulted.")
    align_rusle_factors(factors);grid=factors["R"]["grid"];base=calculate_rusle_soil_loss(*(factors[x]["data"] for x in ("R","K","LS","C_baseline","P_baseline")));scenario=calculate_rusle_soil_loss(*(factors[x]["data"] for x in ("R","K","LS","C_conservation","P_conservation")));conservation=calculate_soil_conservation_amount(base,scenario)
    _write_grid(root/"soil_loss_baseline.asc",base,grid);_write_grid(root/"soil_loss_scenario.asc",scenario,grid);_write_grid(root/"soil_conservation_amount.asc",conservation,grid)
    stat=calculate_rusle_statistics(base);sstat=calculate_rusle_statistics(scenario);stat["baseline_total_t_yr"]=stat["total_soil_loss_t_yr"];stat["scenario_total_t_yr"]=float(np.nansum(scenario));stat["soil_conservation_t_yr"]=float(np.nansum(conservation));stat["soil_conservation_percent"]=float(np.nansum(conservation)/np.nansum(base)*100);sstat["subbasin_id"]="all"
    summary=pd.DataFrame([{"factor_name":k,**v["metadata"]} for k,v in factors.items()]);quality=pd.DataFrame([validate_rusle_factor(v,k) for k,v in factors.items()])
    with pd.ExcelWriter(root/"factor_summary.xlsx") as w:summary.to_excel(w,index=False)
    with pd.ExcelWriter(root/"factor_quality.xlsx") as w:quality.to_excel(w,index=False)
    with pd.ExcelWriter(root/"subbasin_soil_loss.xlsx") as w:stat.to_excel(w,index=False)
    with pd.ExcelWriter(root/"subbasin_conservation.xlsx") as w:stat.to_excel(w,index=False)
    with pd.ExcelWriter(root/"erosion_class_area.xlsx") as w:pd.Series(classify_rusle_erosion_intensity(base).ravel()).value_counts().rename_axis("erosion_class").reset_index(name="cell_count").to_excel(w,index=False)
    charts=root/"charts";charts.mkdir(exist_ok=True)
    for name,array in [("soil_loss_baseline.png",base),("soil_conservation.png",conservation)]:
        fig,ax=plt.subplots();im=ax.imshow(array);fig.colorbar(im,ax=ax);fig.tight_layout();fig.savefig(charts/name,dpi=120);plt.close(fig)
    zh=root/"rusle_report_zh.md";zh.write_text("# RUSLE 土壤侵蚀报告\n\n结果为年平均片蚀和细沟侵蚀量，不是入河泥沙、单场洪水侵蚀或河道输沙。\n");en=root/"rusle_report_en.md";en.write_text("# RUSLE report\n\nAnnual average sheet and rill soil loss only; not sediment delivery.\n")
    (root/"rusle_diagnosis.md").write_text("# RUSLE diagnosis\n\nSynthetic local factor demo.\n");(root/"rusle_manifest.json").write_text(json.dumps({"synthetic_demo":True,"status":"partial","config":config_file.name},indent=2)+"\n")
    return {"status":"partial","baseline_total_t_yr":float(np.nansum(base)),"scenario_total_t_yr":float(np.nansum(scenario)),"soil_conservation_t_yr":float(np.nansum(conservation)),"soil_conservation_percent":float(np.nansum(conservation)/np.nansum(base)*100),"subbasin_statistics":stat,"output_dir":root}
def write_rusle_outputs(output_dir:str|Path,result:dict[str,Any])->Path:return _path(output_dir)/"rusle_report_zh.md"
def validate_rusle_outputs(output_dir:str|Path)->dict[str,Any]:
    r=_path(output_dir);need=["factor_summary.xlsx","factor_quality.xlsx","soil_loss_baseline.asc","soil_loss_scenario.asc","soil_conservation_amount.asc","subbasin_soil_loss.xlsx","rusle_report_zh.md","rusle_report_en.md"];missing=[x for x in need if not (r/x).exists()];return {"status":"passed" if not missing else "failed","missing":missing}
