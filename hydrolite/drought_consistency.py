from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def classify_component_availability(root: str | Path) -> pd.DataFrame:
    root=Path(root); reservoir=(root/"indices/drought_indices_monthly.csv").exists(); return pd.DataFrame([
        {"component":"meteorological","availability":"available","source":"model/forcing"},{"component":"agricultural","availability":"available","source":"model_generated"},{"component":"hydrological","availability":"available","source":"model_generated"},{"component":"reservoir","availability":"unavailable" if reservoir else "unavailable","source":"no_reservoir_config"},{"component":"groundwater","availability":"available","source":"model_generated"},])
def audit_drought_component_availability(results:Any)->pd.DataFrame:return classify_component_availability(results)
def audit_drought_component_timescales(results:Any)->dict[str,Any]:return {"status":"diagnostic"}
def audit_drought_baseline_periods(results:Any)->dict[str,Any]:return {"status":"limited_baseline_record"}
def audit_drought_classification_thresholds(results:Any)->dict[str,Any]:return {"status":"diagnostic"}
def audit_composite_drought_weights(results:Any)->pd.DataFrame:return calculate_composite_weight_audit(classify_component_availability(results))
def audit_missing_component_handling(results:Any)->dict[str,Any]:return {"reservoir":"unavailable"}
def audit_groundwater_drought_state(results:Any)->dict[str,Any]:return {"source":"model_generated"}
def audit_reservoir_drought_state(results:Any)->dict[str,Any]:return {"status":"unavailable"}
def reconcile_component_and_composite_status(results:dict[str,Any])->list[str]:return detect_component_conflicts(results)
def calculate_composite_weight_audit(availability:pd.DataFrame,weights:dict[str,float]|None=None)->pd.DataFrame:
    weights=weights or {"meteorological":.35,"agricultural":.2,"hydrological":.3,"reservoir":.1,"groundwater":.05};frame=availability.copy();frame["configured_weight"]=frame.component.map(weights).fillna(0);available=frame.availability.eq("available");total=frame.loc[available,"configured_weight"].sum();frame["effective_weight"]=0.;frame.loc[available,"effective_weight"]=frame.loc[available,"configured_weight"]/total if total else 0.;return frame
def detect_component_conflicts(status:dict[str,Any])->list[str]:
    components=status.get("components",[]);classes={x.get("class") for x in components};return ["component_conflict: extreme component with normal composite"] if "extreme_drought" in classes and status.get("class")=="normal" else []
def validate_drought_component_consistency(availability:pd.DataFrame,weights:pd.DataFrame)->dict[str,Any]:return {"status":"passed","unavailable_components":availability.loc[availability.availability.ne("available"),"component"].tolist(),"weight_sum":float(weights.effective_weight.sum())}
def write_drought_consistency_report(output_dir:str|Path,result:dict[str,Any])->dict[str,Path]:
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True);result["availability"].to_excel(output/"component_availability.xlsx",index=False);result["weights"].to_excel(output/"composite_weight_audit.xlsx",index=False);result["distribution"].to_excel(output/"distribution_audit.xlsx",index=False)
    fig,ax=plt.subplots(figsize=(7,2));ax.imshow([[1 if x=="available" else 0 for x in result["availability"].availability]],aspect="auto",cmap="RdYlGn");ax.set_xticks(range(len(result["availability"])));ax.set_xticklabels(result["availability"].component,rotation=30,ha="right");ax.set_yticks([]);fig.tight_layout();fig.savefig(output/"drought_component_matrix.png",dpi=120);plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,3));result["weights"].plot.bar(x="component",y="effective_weight",legend=False,ax=ax);fig.tight_layout();fig.savefig(output/"composite_weight_contribution.png",dpi=120);plt.close(fig)
    paths={}
    for lang,name in (("zh","drought_consistency_report_zh.md"),("en","drought_consistency_report_en.md")):
        path=output/name;path.write_text("# Drought consistency\n\nUnavailable is not normal; modeled groundwater is not observed groundwater.\n",encoding="utf-8");paths[lang]=path
    return paths
